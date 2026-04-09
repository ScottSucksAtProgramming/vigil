"""Shared pytest fixtures for grandma-watcher tests."""

from pathlib import Path

import pytest

from models import (
    AssessmentResult,
    Confidence,
    PatientLocation,
    SensorSnapshot,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Frame fixtures — stand in for go2rtc JPEG frames
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_frame_bytes() -> bytes:
    """Minimal valid JPEG bytes, simulating a frame from go2rtc."""
    return (FIXTURES_DIR / "frame.jpeg").read_bytes()


@pytest.fixture
def fixture_frame_path() -> Path:
    """Path to the fixture JPEG."""
    return FIXTURES_DIR / "frame.jpeg"


# ---------------------------------------------------------------------------
# Model stubs — reusable across unit and integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def safe_assessment() -> AssessmentResult:
    return AssessmentResult(
        safe=True,
        confidence=Confidence.HIGH,
        reason="Patient resting in bed.",
        patient_location=PatientLocation.IN_BED,
    )


@pytest.fixture
def unsafe_assessment() -> AssessmentResult:
    return AssessmentResult(
        safe=False,
        confidence=Confidence.HIGH,
        reason="Patient appears to be out of bed.",
        patient_location=PatientLocation.OUT_OF_BED,
    )


@pytest.fixture
def phase1_sensor_snapshot() -> SensorSnapshot:
    """Phase 1 snapshot — both sensor types disabled."""
    return SensorSnapshot(load_cells_enabled=False, vitals_enabled=False)
