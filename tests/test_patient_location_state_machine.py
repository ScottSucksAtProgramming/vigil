"""Tests for PatientLocationStateMachine in alert.py."""

import enum

import pytest

from alert import PatientLocationStateMachine, SilenceEvent
from models import AssessmentResult, Confidence, PatientLocation


class FakePatientLocation(enum.Enum):
    OTHER = "other"


def _make_assessment(location: PatientLocation) -> AssessmentResult:
    return AssessmentResult(
        safe=True,
        confidence=Confidence.HIGH,
        reason="Test.",
        patient_location=location,
    )


def _make_psm(
    *,
    out_threshold: int = 3,
    in_threshold: int = 2,
) -> PatientLocationStateMachine:
    return PatientLocationStateMachine(
        out_of_bed_frames_to_silence=out_threshold,
        in_bed_frames_to_resume=in_threshold,
    )


def _trigger_silence(psm: PatientLocationStateMachine) -> None:
    for _ in range(psm._out_of_bed_threshold):
        psm.push(_make_assessment(PatientLocation.OUT_OF_BED))


def test_silence_event_has_activate_and_resume_values():
    assert SilenceEvent.ACTIVATE.value == "activate"
    assert SilenceEvent.RESUME.value == "resume"


def test_psm_initial_auto_silenced_is_false():
    psm = PatientLocationStateMachine(
        out_of_bed_frames_to_silence=3,
        in_bed_frames_to_resume=2,
    )
    assert psm.auto_silenced is False


def test_psm_out_of_bed_below_threshold_returns_none():
    psm = _make_psm(out_threshold=3)
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm._consecutive_out_of_bed == 2


def test_psm_out_of_bed_at_threshold_returns_activate():
    psm = _make_psm(out_threshold=3)
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) == SilenceEvent.ACTIVATE


def test_psm_auto_silenced_true_after_activate():
    psm = _make_psm(out_threshold=3)
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    assert psm.auto_silenced is True


def test_psm_activate_fires_once_then_none():
    psm = _make_psm(out_threshold=3)
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None


def test_psm_in_bed_below_resume_threshold_returns_none():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) is None
    assert psm._consecutive_in_bed == 1


def test_psm_in_bed_at_resume_threshold_returns_resume():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    psm.push(_make_assessment(PatientLocation.IN_BED))
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) == SilenceEvent.RESUME


def test_psm_auto_silenced_false_after_resume():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    psm.push(_make_assessment(PatientLocation.IN_BED))
    psm.push(_make_assessment(PatientLocation.IN_BED))
    assert psm.auto_silenced is False


def test_psm_resume_fires_once_then_none():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    psm.push(_make_assessment(PatientLocation.IN_BED))
    psm.push(_make_assessment(PatientLocation.IN_BED))
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) is None


def test_psm_in_bed_before_silence_never_returns_resume():
    psm = _make_psm(in_threshold=2)
    for _ in range(5):
        assert psm.push(_make_assessment(PatientLocation.IN_BED)) is None


def test_psm_unknown_counts_as_in_bed_for_resume():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    psm.push(_make_assessment(PatientLocation.UNKNOWN))
    assert psm.push(_make_assessment(PatientLocation.UNKNOWN)) == SilenceEvent.RESUME


def test_psm_unknown_resets_out_of_bed_counter():
    psm = _make_psm(out_threshold=3)
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.UNKNOWN))
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None


def test_psm_being_assisted_out_resets_out_of_bed_counter():
    psm = _make_psm(out_threshold=3)
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.BEING_ASSISTED_OUT))
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None


def test_psm_being_assisted_out_resets_in_bed_counter():
    psm = _make_psm(in_threshold=2)
    _trigger_silence(psm)
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.BEING_ASSISTED_OUT)) is None
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) is None


def test_psm_can_reactivate_after_resume():
    psm = _make_psm(out_threshold=3, in_threshold=2)
    _trigger_silence(psm)
    psm.push(_make_assessment(PatientLocation.IN_BED))
    psm.push(_make_assessment(PatientLocation.IN_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) == SilenceEvent.ACTIVATE


def test_psm_push_returns_silence_event_or_none():
    psm = _make_psm(out_threshold=3, in_threshold=2)
    results = [
        psm.push(_make_assessment(PatientLocation.OUT_OF_BED)),
        psm.push(_make_assessment(PatientLocation.OUT_OF_BED)),
        psm.push(_make_assessment(PatientLocation.OUT_OF_BED)),
        psm.push(_make_assessment(PatientLocation.IN_BED)),
        psm.push(_make_assessment(PatientLocation.IN_BED)),
        psm.push(_make_assessment(PatientLocation.BEING_ASSISTED_OUT)),
    ]
    for result in results:
        assert result is None or isinstance(result, SilenceEvent)


def test_psm_out_of_bed_while_silenced_does_not_cause_premature_reactivate():
    psm = _make_psm(out_threshold=3, in_threshold=2)
    _trigger_silence(psm)
    assert psm._consecutive_out_of_bed == 0
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.OUT_OF_BED))
    psm.push(_make_assessment(PatientLocation.IN_BED))
    psm.push(_make_assessment(PatientLocation.IN_BED))
    assert psm._consecutive_in_bed == 0
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) is None
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) == SilenceEvent.ACTIVATE


def test_psm_init_raises_value_error_for_zero_threshold():
    with pytest.raises(ValueError):
        PatientLocationStateMachine(
            out_of_bed_frames_to_silence=0,
            in_bed_frames_to_resume=2,
        )

    with pytest.raises(ValueError):
        PatientLocationStateMachine(
            out_of_bed_frames_to_silence=3,
            in_bed_frames_to_resume=0,
        )


def test_psm_threshold_one_activates_and_resumes_immediately():
    psm = _make_psm(out_threshold=1, in_threshold=1)
    assert psm.push(_make_assessment(PatientLocation.OUT_OF_BED)) == SilenceEvent.ACTIVATE
    assert psm.push(_make_assessment(PatientLocation.IN_BED)) == SilenceEvent.RESUME


def test_psm_push_raises_for_unexpected_patient_location():
    psm = _make_psm()
    with pytest.raises(ValueError, match="Unexpected PatientLocation"):
        psm.push(_make_assessment(FakePatientLocation.OTHER))
