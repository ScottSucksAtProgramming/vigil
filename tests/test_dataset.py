import dataclasses
import json

import pytest

from config import AppConfig, DatasetConfig
from models import AssessmentResult, Confidence, DatasetEntry, PatientLocation, SensorSnapshot


def _dataset_config(tmp_path):
    base_dir = tmp_path / "dataset"
    return DatasetConfig(
        base_dir=str(base_dir),
        images_dir=str(base_dir / "images"),
        log_file=str(base_dir / "log.jsonl"),
        checkin_log_file=str(base_dir / "checkins.jsonl"),
    )


def _app_config(sample_config: AppConfig, tmp_path) -> AppConfig:
    return dataclasses.replace(sample_config, dataset=_dataset_config(tmp_path))


def _dataset_entry(**overrides) -> DatasetEntry:
    defaults = dict(
        timestamp="2026-04-09T03:00:00Z",
        image_path="",
        provider="openrouter",
        model="qwen/qwen3-vl-32b-instruct",
        prompt_version="1.0",
        sensor_snapshot=SensorSnapshot(load_cells_enabled=False, vitals_enabled=False),
        response_raw='{"safe": true, "confidence": "high"}',
        assessment=AssessmentResult(
            safe=True,
            confidence=Confidence.HIGH,
            reason="Patient resting in bed.",
            patient_location=PatientLocation.IN_BED,
        ),
        alert_fired=False,
        api_latency_ms=2140.0,
    )
    return DatasetEntry(**{**defaults, **overrides})


def test_build_image_filename_formats_iso_utc_timestamp():
    from dataset import build_image_filename

    assert build_image_filename("2026-04-09T03:00:00Z") == "2026-04-09_03-00-00.jpg"


def test_build_image_filename_rejects_malformed_timestamp():
    from dataset import build_image_filename

    with pytest.raises(ValueError, match="timestamp"):
        build_image_filename("2026-04-09 03:00:00")


def test_save_frame_image_writes_exact_bytes(sample_config, tmp_path, fixture_frame_bytes):
    from dataset import save_frame_image

    config = _app_config(sample_config, tmp_path)

    relative_path = save_frame_image(
        config=config,
        timestamp="2026-04-09T03:00:00Z",
        frame_bytes=fixture_frame_bytes,
    )

    assert relative_path == "images/2026-04-09_03-00-00.jpg"
    image_path = tmp_path / "dataset" / relative_path
    assert image_path.exists()
    assert image_path.read_bytes() == fixture_frame_bytes


def test_append_log_entry_writes_single_json_line(sample_config, tmp_path):
    from dataset import append_log_entry

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(image_path="images/2026-04-09_03-00-00.jpg")

    append_log_entry(config, entry)

    log_path = tmp_path / "dataset" / "log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_append_log_entry_serializes_nested_enums_to_strings(sample_config, tmp_path):
    from dataset import append_log_entry

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry(image_path="images/2026-04-09_03-00-00.jpg")

    append_log_entry(config, entry)

    payload = json.loads((tmp_path / "dataset" / "log.jsonl").read_text(encoding="utf-8"))
    assert payload["assessment"]["confidence"] == "high"
    assert payload["assessment"]["patient_location"] == "in_bed"
    assert payload["sensor_snapshot"]["load_cells_enabled"] is False
    assert payload["sensor_snapshot"]["vitals_enabled"] is False


def test_record_dataset_entry_writes_image_and_log_row(
    sample_config, tmp_path, fixture_frame_bytes
):
    from dataset import record_dataset_entry

    config = _app_config(sample_config, tmp_path)
    entry = _dataset_entry()

    saved_entry = record_dataset_entry(
        config=config,
        timestamp="2026-04-09T03:00:00Z",
        frame_bytes=fixture_frame_bytes,
        entry=entry,
    )

    assert saved_entry.image_path == "images/2026-04-09_03-00-00.jpg"
    assert (tmp_path / "dataset" / "images" / "2026-04-09_03-00-00.jpg").exists()

    payload = json.loads((tmp_path / "dataset" / "log.jsonl").read_text(encoding="utf-8"))
    assert payload["image_path"] == "images/2026-04-09_03-00-00.jpg"
    assert payload["assessment"]["reason"] == "Patient resting in bed."
