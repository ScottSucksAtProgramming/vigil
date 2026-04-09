"""Tests for vlm_parser.py — pure function, no I/O."""

import json

import pytest

from models import AssessmentResult, Confidence, PatientLocation
from vlm_parser import VLMParseError, parse_vlm_response

# ---------------------------------------------------------------------------
# Helpers — minimal valid JSON strings
# ---------------------------------------------------------------------------


def _make_raw(
    *,
    safe: object = True,
    confidence: object = "high",
    reason: object = "Patient resting in bed.",
    patient_location: object = "in_bed",
    **extra,
) -> str:
    data: dict = {
        "safe": safe,
        "confidence": confidence,
        "reason": reason,
        "patient_location": patient_location,
    }
    data.update(extra)
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_parse_minimal_valid():
    result = parse_vlm_response(_make_raw())
    assert isinstance(result, AssessmentResult)
    assert result.safe is True
    assert result.confidence == Confidence.HIGH
    assert result.reason == "Patient resting in bed."
    assert result.patient_location == PatientLocation.IN_BED
    assert result.sensor_notes == ""


def test_parse_with_sensor_notes():
    raw = _make_raw(sensor_notes="Weight shift detected on left load cells.")
    result = parse_vlm_response(raw)
    assert result.sensor_notes == "Weight shift detected on left load cells."


def test_parse_safe_false():
    result = parse_vlm_response(_make_raw(safe=False, patient_location="out_of_bed"))
    assert result.safe is False


def test_parse_confidence_high():
    result = parse_vlm_response(_make_raw(confidence="high"))
    assert result.confidence == Confidence.HIGH


def test_parse_confidence_medium():
    result = parse_vlm_response(_make_raw(confidence="medium"))
    assert result.confidence == Confidence.MEDIUM


def test_parse_confidence_low():
    result = parse_vlm_response(_make_raw(confidence="low"))
    assert result.confidence == Confidence.LOW


@pytest.mark.parametrize(
    "location_str, expected",
    [
        ("in_bed", PatientLocation.IN_BED),
        ("being_assisted_out", PatientLocation.BEING_ASSISTED_OUT),
        ("out_of_bed", PatientLocation.OUT_OF_BED),
        ("unknown", PatientLocation.UNKNOWN),
    ],
)
def test_parse_all_patient_location_values(location_str, expected):
    result = parse_vlm_response(_make_raw(patient_location=location_str))
    assert result.patient_location == expected


def test_parse_extra_keys_ignored():
    raw = _make_raw(chain_of_thought="The patient is clearly visible on the left side of the bed.")
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


def test_parse_sensor_notes_empty_string():
    result = parse_vlm_response(_make_raw(sensor_notes=""))
    assert result.sensor_notes == ""


def test_parse_sensor_notes_null():
    raw = _make_raw(sensor_notes=None)
    result = parse_vlm_response(raw)
    assert result.sensor_notes == ""


def test_parse_sensor_notes_absent():
    result = parse_vlm_response(_make_raw())
    assert result.sensor_notes == ""


def test_parse_whitespace_around_json():
    result = parse_vlm_response("   " + _make_raw() + "   ")
    assert isinstance(result, AssessmentResult)


def test_parse_unicode_in_reason():
    result = parse_vlm_response(_make_raw(reason="Patiente está en cama"))
    assert result.reason == "Patiente está en cama"


def test_parse_unicode_in_sensor_notes():
    result = parse_vlm_response(_make_raw(sensor_notes="Détecteur: aucun mouvement"))
    assert result.sensor_notes == "Détecteur: aucun mouvement"


def test_parse_confidence_uppercase():
    result = parse_vlm_response(_make_raw(confidence="HIGH"))
    assert result.confidence == Confidence.HIGH


def test_parse_patient_location_uppercase():
    result = parse_vlm_response(_make_raw(patient_location="IN_BED"))
    assert result.patient_location == PatientLocation.IN_BED


# ---------------------------------------------------------------------------
# Fence stripping
# ---------------------------------------------------------------------------


def test_parse_fenced_json_with_language_tag():
    raw = "```json\n" + _make_raw() + "\n```"
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


def test_parse_fenced_json_no_language_tag():
    raw = "```\n" + _make_raw() + "\n```"
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


def test_parse_fenced_json_uppercase_tag():
    raw = "```JSON\n" + _make_raw() + "\n```"
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


def test_parse_fenced_json_no_newlines():
    raw = "```json" + _make_raw() + "```"
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


def test_parse_fenced_json_extra_whitespace():
    raw = "```json\n\n\n" + _make_raw() + "\n\n\n```"
    result = parse_vlm_response(raw)
    assert isinstance(result, AssessmentResult)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_invalid_json():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("not json")
    assert exc_info.value.reason == "invalid JSON"


def test_empty_string_input():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("")
    assert exc_info.value.reason == "invalid JSON"


def test_json_array():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("[1, 2, 3]")
    assert exc_info.value.reason.startswith("expected JSON object, got list")


def test_empty_dict():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("{}")
    assert exc_info.value.reason == "missing field: safe"


def test_missing_field_confidence():
    data = {"safe": True, "reason": "ok", "patient_location": "in_bed"}
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(json.dumps(data))
    assert exc_info.value.reason == "missing field: confidence"


def test_missing_field_reason():
    data = {"safe": True, "confidence": "high", "patient_location": "in_bed"}
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(json.dumps(data))
    assert exc_info.value.reason == "missing field: reason"


def test_missing_field_patient_location():
    data = {"safe": True, "confidence": "high", "reason": "ok"}
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(json.dumps(data))
    assert exc_info.value.reason == "missing field: patient_location"


def test_safe_wrong_type_string():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(safe="true"))
    assert "wrong type for safe" in exc_info.value.reason


def test_safe_integer_not_accepted():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(safe=1))
    assert "wrong type for safe" in exc_info.value.reason
    assert "got int" in exc_info.value.reason


def test_safe_null():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(safe=None))
    assert "wrong type for safe" in exc_info.value.reason


def test_confidence_wrong_type():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(confidence=42))
    assert "wrong type for confidence" in exc_info.value.reason


def test_confidence_unknown_value():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(confidence="very_high"))
    assert "unknown confidence value" in exc_info.value.reason


def test_reason_wrong_type():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(reason=True))
    assert "wrong type for reason" in exc_info.value.reason


def test_reason_empty_string():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(reason=""))
    assert exc_info.value.reason == "reason field is empty"


def test_reason_whitespace_only():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(reason="   "))
    assert exc_info.value.reason == "reason field is empty"


def test_patient_location_unknown_value():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(patient_location="floating"))
    assert "unknown patient_location value" in exc_info.value.reason


def test_sensor_notes_wrong_type():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(sensor_notes=99))
    assert "wrong type for sensor_notes" in exc_info.value.reason


def test_safe_nested_object_rejected():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(_make_raw(safe={"nested": True}))
    assert "wrong type for safe" in exc_info.value.reason


def test_vlm_parse_error_carries_raw():
    raw = "not json"
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response(raw)
    assert exc_info.value.raw == raw


def test_vlm_parse_error_is_exception():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("not json")
    assert isinstance(exc_info.value, Exception)


def test_vlm_parse_error_str():
    with pytest.raises(VLMParseError) as exc_info:
        parse_vlm_response("not json")
    e = exc_info.value
    assert str(e) == e.reason
