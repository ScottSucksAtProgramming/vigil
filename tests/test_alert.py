"""Tests for decide_alert_type() in alert.py.

Decision rules (first-match):
  Rule 1 — safe:          return None regardless of confidence
  Rule 2 — HIGH unsafe:   return UNSAFE_HIGH, bypasses all suppression
  Rule 3 — MEDIUM unsafe: suppressed by silence or cooldown; fires at threshold
  Rule 4 — LOW unsafe:    suppressed by silence or cooldown; fires at threshold
  Fallthrough:            raises ValueError for unknown Confidence value
"""

import enum

import pytest

from alert import decide_alert_type
from config import AlertsConfig
from models import AlertType, AssessmentResult, Confidence, PatientLocation

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_assessment(
    *,
    safe: bool = False,
    confidence: Confidence = Confidence.HIGH,
    reason: str = "Test.",
    patient_location: PatientLocation = PatientLocation.OUT_OF_BED,
) -> AssessmentResult:
    return AssessmentResult(
        safe=safe,
        confidence=confidence,
        reason=reason,
        patient_location=patient_location,
    )


def _make_config(*, medium_threshold: int = 2, low_threshold: int = 3) -> AlertsConfig:
    return AlertsConfig(
        medium_unsafe_window_threshold=medium_threshold,
        low_unsafe_window_threshold=low_threshold,
    )


def _call(
    assessment: AssessmentResult,
    *,
    medium_count: int = 0,
    low_count: int = 0,
    silence: bool = False,
    medium_cd: bool = False,
    low_cd: bool = False,
    config: AlertsConfig | None = None,
) -> AlertType | None:
    return decide_alert_type(
        assessment,
        medium_unsafe_in_window=medium_count,
        low_unsafe_in_window=low_count,
        silence_active=silence,
        medium_cooldown_active=medium_cd,
        low_cooldown_active=low_cd,
        config=config or _make_config(),
    )


# ---------------------------------------------------------------------------
# Rule 1 — Safe (tests 1–6)
# ---------------------------------------------------------------------------


def test_01_safe_high_returns_none():
    assert _call(_make_assessment(safe=True, confidence=Confidence.HIGH)) is None


def test_02_safe_medium_returns_none():
    assert _call(_make_assessment(safe=True, confidence=Confidence.MEDIUM)) is None


def test_03_safe_low_returns_none():
    assert _call(_make_assessment(safe=True, confidence=Confidence.LOW)) is None


def test_04_safe_with_silence_returns_none():
    assert _call(_make_assessment(safe=True), silence=True) is None


def test_05_safe_with_counts_returns_none():
    assert _call(_make_assessment(safe=True), medium_count=10, low_count=10) is None


def test_06_safe_with_cooldowns_returns_none():
    assert _call(_make_assessment(safe=True), medium_cd=True, low_cd=True) is None


# ---------------------------------------------------------------------------
# Rule 2 — HIGH confidence unsafe (tests 7–12)
# ---------------------------------------------------------------------------


def test_07_high_unsafe_returns_unsafe_high():
    assert _call(_make_assessment(confidence=Confidence.HIGH)) == AlertType.UNSAFE_HIGH


def test_08_high_unsafe_ignores_silence():
    assert (
        _call(_make_assessment(confidence=Confidence.HIGH), silence=True) == AlertType.UNSAFE_HIGH
    )


def test_09_high_unsafe_ignores_medium_cooldown():
    assert (
        _call(_make_assessment(confidence=Confidence.HIGH), medium_cd=True) == AlertType.UNSAFE_HIGH
    )


def test_10_high_unsafe_ignores_low_cooldown():
    assert _call(_make_assessment(confidence=Confidence.HIGH), low_cd=True) == AlertType.UNSAFE_HIGH


def test_11_high_unsafe_ignores_window_counts():
    assert (
        _call(_make_assessment(confidence=Confidence.HIGH), medium_count=0, low_count=0)
        == AlertType.UNSAFE_HIGH
    )


def test_12_high_unsafe_all_suppression_active_still_fires():
    assert (
        _call(
            _make_assessment(confidence=Confidence.HIGH),
            silence=True,
            medium_cd=True,
            low_cd=True,
            medium_count=0,
            low_count=0,
        )
        == AlertType.UNSAFE_HIGH
    )


# ---------------------------------------------------------------------------
# Rule 3 — MEDIUM confidence unsafe (tests 13–23)
# ---------------------------------------------------------------------------


def test_13_medium_below_threshold_returns_none():
    assert _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=1) is None


def test_14_medium_at_threshold_returns_unsafe_medium():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=2)
        == AlertType.UNSAFE_MEDIUM
    )


def test_15_medium_above_threshold_returns_unsafe_medium():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=5)
        == AlertType.UNSAFE_MEDIUM
    )


def test_16_medium_silence_active_returns_none():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), silence=True, medium_count=5) is None
    )


def test_17_medium_cooldown_active_returns_none():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_cd=True, medium_count=5)
        is None
    )


def test_18_medium_silence_takes_priority_over_cooldown():
    assert (
        _call(
            _make_assessment(confidence=Confidence.MEDIUM),
            silence=True,
            medium_cd=True,
            medium_count=5,
        )
        is None
    )


def test_19_medium_zero_count_returns_none():
    assert _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=0) is None


def test_20_medium_custom_threshold_below():
    cfg = _make_config(medium_threshold=4)
    assert _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=3, config=cfg) is None


def test_21_medium_custom_threshold_at():
    cfg = _make_config(medium_threshold=4)
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=4, config=cfg)
        == AlertType.UNSAFE_MEDIUM
    )


def test_22_medium_low_cooldown_does_not_suppress_medium():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), low_cd=True, medium_count=2)
        == AlertType.UNSAFE_MEDIUM
    )


def test_23_medium_returns_none_when_no_suppression_and_below_threshold():
    assert _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=0) is None


# ---------------------------------------------------------------------------
# Rule 4 — LOW confidence unsafe (tests 24–34)
# ---------------------------------------------------------------------------


def test_24_low_below_threshold_returns_none():
    assert _call(_make_assessment(confidence=Confidence.LOW), low_count=2) is None


def test_25_low_at_threshold_returns_soft_low():
    assert (
        _call(_make_assessment(confidence=Confidence.LOW), low_count=3)
        == AlertType.SOFT_LOW_CONFIDENCE
    )


def test_26_low_above_threshold_returns_soft_low():
    assert (
        _call(_make_assessment(confidence=Confidence.LOW), low_count=10)
        == AlertType.SOFT_LOW_CONFIDENCE
    )


def test_27_low_silence_active_returns_none():
    assert _call(_make_assessment(confidence=Confidence.LOW), silence=True, low_count=10) is None


def test_28_low_cooldown_active_returns_none():
    assert _call(_make_assessment(confidence=Confidence.LOW), low_cd=True, low_count=10) is None


def test_29_low_silence_takes_priority_over_cooldown():
    assert (
        _call(
            _make_assessment(confidence=Confidence.LOW),
            silence=True,
            low_cd=True,
            low_count=10,
        )
        is None
    )


def test_30_low_zero_count_returns_none():
    assert _call(_make_assessment(confidence=Confidence.LOW), low_count=0) is None


def test_31_low_custom_threshold_below():
    cfg = _make_config(low_threshold=5)
    assert _call(_make_assessment(confidence=Confidence.LOW), low_count=4, config=cfg) is None


def test_32_low_custom_threshold_at():
    cfg = _make_config(low_threshold=5)
    assert (
        _call(_make_assessment(confidence=Confidence.LOW), low_count=5, config=cfg)
        == AlertType.SOFT_LOW_CONFIDENCE
    )


def test_33_low_medium_cooldown_does_not_suppress_low():
    assert (
        _call(_make_assessment(confidence=Confidence.LOW), medium_cd=True, low_count=3)
        == AlertType.SOFT_LOW_CONFIDENCE
    )


def test_34_low_returns_none_when_no_suppression_and_below_threshold():
    assert _call(_make_assessment(confidence=Confidence.LOW), low_count=0) is None


# ---------------------------------------------------------------------------
# Cross-rule isolation (tests 35–38)
# ---------------------------------------------------------------------------


def test_35_medium_count_does_not_affect_low_rule():
    assert _call(_make_assessment(confidence=Confidence.LOW), medium_count=99, low_count=0) is None


def test_36_low_count_does_not_affect_medium_rule():
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), low_count=99, medium_count=0) is None
    )


def test_37_return_type_is_alert_type_for_medium():
    result = _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=2)
    assert isinstance(result, AlertType)


def test_38_return_type_is_alert_type_for_low():
    result = _call(_make_assessment(confidence=Confidence.LOW), low_count=3)
    assert isinstance(result, AlertType)


# ---------------------------------------------------------------------------
# Boundary — threshold at window size (tests 39–40)
# ---------------------------------------------------------------------------


def test_39_medium_threshold_equals_window_size():
    cfg = _make_config(medium_threshold=5)
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=5, config=cfg)
        == AlertType.UNSAFE_MEDIUM
    )


def test_40_low_threshold_equals_window_size():
    cfg = _make_config(low_threshold=5)
    assert (
        _call(_make_assessment(confidence=Confidence.LOW), low_count=5, config=cfg)
        == AlertType.SOFT_LOW_CONFIDENCE
    )


# ---------------------------------------------------------------------------
# NEW — threshold at 0 (test 41)
# ---------------------------------------------------------------------------


def test_41_medium_threshold_zero_fires_immediately():
    """threshold=0, count=0 → 0 >= 0 → UNSAFE_MEDIUM fires immediately."""
    cfg = _make_config(medium_threshold=0)
    assert (
        _call(_make_assessment(confidence=Confidence.MEDIUM), medium_count=0, config=cfg)
        == AlertType.UNSAFE_MEDIUM
    )


# ---------------------------------------------------------------------------
# NEW — unknown confidence raises ValueError (test 42)
# ---------------------------------------------------------------------------


def test_42_unknown_confidence_raises_value_error():
    """Defensive fallthrough: an unrecognised Confidence value raises ValueError."""
    FakeConfidence = enum.Enum("FakeConfidence", {"UNKNOWN": "unknown"})
    bad_assessment = AssessmentResult(
        safe=False,
        confidence=FakeConfidence.UNKNOWN,  # type: ignore[arg-type]
        reason="Test.",
        patient_location=PatientLocation.OUT_OF_BED,
    )
    with pytest.raises(ValueError, match="Unexpected confidence value"):
        _call(bad_assessment)
