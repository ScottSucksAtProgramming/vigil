import dataclasses
import json
from collections import deque

from alert import CooldownTimer, PatientLocationStateMachine, SlidingWindowCounter
from config import AppConfig, DatasetConfig
from models import Alert, AlertType, AssessmentResult, Confidence, PatientLocation
from monitor import run_cycle


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


def _read_log_rows(tmp_path):
    log_path = tmp_path / "dataset" / "log.jsonl"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def test_safe_cycle_integration_writes_files_and_passes_prompt(
    sample_config, tmp_path, fixture_frame_bytes
):
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

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **_state(config),
    )

    assert channel.alerts == []
    assert len(provider.calls) == 1
    frame, prompt = provider.calls[0]
    assert frame == fixture_frame_bytes
    assert "97 years old" in prompt
    assert "Parkinson's" in prompt

    rows = _read_log_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["alert_fired"] is False
    assert (tmp_path / "dataset" / rows[0]["image_path"]).exists()


def test_high_unsafe_cycle_integration_sends_alert_and_logs_alert_fired(
    sample_config, tmp_path, fixture_frame_bytes
):
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

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **_state(config),
    )

    assert len(channel.alerts) == 1
    assert channel.alerts[0].alert_type == AlertType.UNSAFE_HIGH
    assert channel.alerts[0].message == "Patient appears stuck against the rail."

    rows = _read_log_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["alert_fired"] is True


def test_medium_threshold_integration_fires_on_second_cycle(
    sample_config, tmp_path, fixture_frame_bytes
):
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
    assert channel.alerts == []

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )

    assert len(channel.alerts) == 1
    assert channel.alerts[0].alert_type == AlertType.UNSAFE_MEDIUM


def test_low_threshold_integration_fires_soft_alert_on_third_cycle(
    sample_config, tmp_path, fixture_frame_bytes
):
    config = _app_config(sample_config, tmp_path)
    provider = _ProviderFake(
        [
            _assessment(
                safe=False,
                confidence=Confidence.LOW,
                reason="Position unclear.",
                patient_location=PatientLocation.IN_BED,
            ),
            _assessment(
                safe=False,
                confidence=Confidence.LOW,
                reason="Position unclear.",
                patient_location=PatientLocation.IN_BED,
            ),
            _assessment(
                safe=False,
                confidence=Confidence.LOW,
                reason="Position unclear.",
                patient_location=PatientLocation.IN_BED,
            ),
        ]
    )
    channel = _AlertChannelFake()
    state = _state(config)

    for _ in range(2):
        run_cycle(
            config,
            provider,
            channel,
            fetch_frame=lambda _config: fixture_frame_bytes,
            **state,
        )
    assert channel.alerts == []

    run_cycle(
        config,
        provider,
        channel,
        fetch_frame=lambda _config: fixture_frame_bytes,
        **state,
    )

    assert len(channel.alerts) == 1
    assert channel.alerts[0].alert_type == AlertType.SOFT_LOW_CONFIDENCE


def test_auto_silence_integration_suppresses_alerts_but_keeps_logging(
    sample_config, tmp_path, fixture_frame_bytes
):
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
    rows = _read_log_rows(tmp_path)
    assert len(rows) == 5
    assert rows[-1]["silence_active"] is True
