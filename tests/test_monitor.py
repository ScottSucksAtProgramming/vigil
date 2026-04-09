import dataclasses
import json
import logging
from collections import deque

import pytest
import requests

from alert import CooldownTimer, PatientLocationStateMachine, SlidingWindowCounter
from config import AppConfig, DatasetConfig
from models import (
    Alert,
    AlertType,
    AssessmentResult,
    Confidence,
    PatientLocation,
)


class _ProviderFake:
    def __init__(self, results):
        self._results = deque(results)
        self.calls = []

    def assess(self, frame: bytes, prompt: str) -> AssessmentResult:
        self.calls.append((frame, prompt))
        return self._results.popleft()


class _AlertChannelFake:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.alerts.append(alert)


def _app_config(sample_config: AppConfig, tmp_path) -> AppConfig:
    base_dir = tmp_path / "dataset"
    dataset = DatasetConfig(
        base_dir=str(base_dir),
        images_dir=str(base_dir / "images"),
        log_file=str(base_dir / "log.jsonl"),
        checkin_log_file=str(base_dir / "checkins.jsonl"),
    )
    return dataclasses.replace(sample_config, dataset=dataset)


def _state(config):
    return dict(
        window_counter=SlidingWindowCounter(config.alerts.window_size),
        medium_cooldown=CooldownTimer(config.alerts.cooldown_minutes * 60),
        low_cooldown=CooldownTimer(config.alerts.low_confidence_cooldown_minutes * 60),
        location_state=PatientLocationStateMachine(
            out_of_bed_frames_to_silence=3,
            in_bed_frames_to_resume=2,
        ),
    )


def _assessment(
    *,
    safe: bool,
    confidence: Confidence,
    reason: str,
    patient_location: PatientLocation,
) -> AssessmentResult:
    return AssessmentResult(
        safe=safe,
        confidence=confidence,
        reason=reason,
        patient_location=patient_location,
    )


def test_fetch_snapshot_uses_configured_snapshot_url(sample_config):
    from monitor import fetch_snapshot

    class _Response:
        content = b"jpeg-bytes"

        def raise_for_status(self) -> None:
            return None

    calls = {}

    def fake_get(url, *, timeout):
        calls["url"] = url
        calls["timeout"] = timeout
        return _Response()

    original_get = requests.get
    requests.get = fake_get
    try:
        result = fetch_snapshot(sample_config)
    finally:
        requests.get = original_get

    assert result == b"jpeg-bytes"
    assert calls["url"] == sample_config.stream.snapshot_url
    assert calls["timeout"] == (
        sample_config.api.timeout_connect_seconds,
        sample_config.api.timeout_read_seconds,
    )


def test_run_cycle_safe_cycle_writes_dataset_and_sends_no_alert(
    sample_config, tmp_path, fixture_frame_bytes
):
    from monitor import run_cycle

    config = _app_config(sample_config, tmp_path)
    provider = _ProviderFake(
        [
            _assessment(
                safe=True,
                confidence=Confidence.HIGH,
                reason="Patient resting in bed.",
                patient_location=PatientLocation.IN_BED,
            )
        ]
    )
    channel = _AlertChannelFake()
    state = _state(config)

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )

    assert channel.alerts == []
    payload = json.loads((tmp_path / "dataset" / "log.jsonl").read_text(encoding="utf-8"))
    assert payload["alert_fired"] is False
    assert payload["provider"] == config.api.provider
    assert payload["model"] == config.api.model
    assert payload["prompt_version"] == config.monitor.prompt_version


def test_run_cycle_high_unsafe_sends_immediate_alert_and_writes_dataset(
    sample_config, tmp_path, fixture_frame_bytes
):
    from monitor import run_cycle

    config = _app_config(sample_config, tmp_path)
    provider = _ProviderFake(
        [
            _assessment(
                safe=False,
                confidence=Confidence.HIGH,
                reason="Patient appears stuck against the rail.",
                patient_location=PatientLocation.IN_BED,
            )
        ]
    )
    channel = _AlertChannelFake()
    state = _state(config)

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )

    assert len(channel.alerts) == 1
    assert channel.alerts[0].alert_type == AlertType.UNSAFE_HIGH
    assert channel.alerts[0].message == "Patient appears stuck against the rail."

    payload = json.loads((tmp_path / "dataset" / "log.jsonl").read_text(encoding="utf-8"))
    assert payload["alert_fired"] is True


def test_run_cycle_medium_threshold_fires_on_second_cycle(
    sample_config, tmp_path, fixture_frame_bytes
):
    from monitor import run_cycle

    config = _app_config(sample_config, tmp_path)
    provider = _ProviderFake(
        [
            _assessment(
                safe=False,
                confidence=Confidence.MEDIUM,
                reason="Patient near bed edge.",
                patient_location=PatientLocation.IN_BED,
            ),
            _assessment(
                safe=False,
                confidence=Confidence.MEDIUM,
                reason="Patient near bed edge.",
                patient_location=PatientLocation.IN_BED,
            ),
        ]
    )
    channel = _AlertChannelFake()
    state = _state(config)

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )
    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )

    assert len(channel.alerts) == 1
    assert channel.alerts[0].alert_type == AlertType.UNSAFE_MEDIUM


def test_run_cycle_auto_silence_flushes_window_and_suppresses_medium_alert(
    sample_config, tmp_path, fixture_frame_bytes
):
    from monitor import run_cycle

    config = _app_config(sample_config, tmp_path)
    provider = _ProviderFake(
        [
            _assessment(
                safe=True,
                confidence=Confidence.HIGH,
                reason="Bed empty.",
                patient_location=PatientLocation.OUT_OF_BED,
            ),
            _assessment(
                safe=True,
                confidence=Confidence.HIGH,
                reason="Bed empty.",
                patient_location=PatientLocation.OUT_OF_BED,
            ),
            _assessment(
                safe=True,
                confidence=Confidence.HIGH,
                reason="Bed empty.",
                patient_location=PatientLocation.OUT_OF_BED,
            ),
            _assessment(
                safe=False,
                confidence=Confidence.MEDIUM,
                reason="Patient near bed edge.",
                patient_location=PatientLocation.OUT_OF_BED,
            ),
            _assessment(
                safe=False,
                confidence=Confidence.MEDIUM,
                reason="Patient near bed edge.",
                patient_location=PatientLocation.OUT_OF_BED,
            ),
        ]
    )
    channel = _AlertChannelFake()
    state = _state(config)

    for _ in range(5):
        run_cycle(
            config,
            provider,
            channel,
            fetch_frame=lambda _config: fixture_frame_bytes,
            **state,
        )

    assert channel.alerts == []
    assert state["location_state"].auto_silenced is True


def test_run_forever_catches_cycle_exception_and_continues(sample_config, caplog):
    from monitor import run_forever

    config = sample_config

    class StopLoop(BaseException):
        pass

    calls = {"run_cycle": 0, "sleep": []}

    def fake_run_cycle(*args, **kwargs):
        calls["run_cycle"] += 1
        if calls["run_cycle"] == 1:
            raise RuntimeError("boom")
        raise StopLoop()

    import monitor

    original_run_cycle = monitor.run_cycle
    original_sleep = monitor.time.sleep
    monitor.run_cycle = fake_run_cycle
    monitor.time.sleep = lambda seconds: calls["sleep"].append(seconds)
    try:
        with caplog.at_level(logging.ERROR, logger="monitor"):
            with pytest.raises(StopLoop):
                run_forever(config, provider=object(), alert_channel=object())
    finally:
        monitor.run_cycle = original_run_cycle
        monitor.time.sleep = original_sleep

    assert calls["run_cycle"] == 2
    assert calls["sleep"] == [config.monitor.interval_seconds]
    assert any("Monitoring cycle failed" in record.message for record in caplog.records)
