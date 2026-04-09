"""Parse and validate VLM JSON responses into AssessmentResult.

No logging, no config, no side effects. Raises VLMParseError on any failure.
Dependency: models.py only.
"""

import json
import re

from models import AssessmentResult, Confidence, PatientLocation

_FENCE_RE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


class VLMParseError(Exception):
    """Raised when a VLM response cannot be parsed or validated.

    Catch on exception type, not on reason string — reason is for logging only.
    """

    def __init__(self, reason: str, raw: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw = raw


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences if present; always strip surrounding whitespace."""
    m = _FENCE_RE.match(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()


def parse_vlm_response(raw: str) -> AssessmentResult:
    """Parse and validate a raw VLM JSON string into an AssessmentResult.

    Raises:
        VLMParseError: On any parse or validation failure — invalid JSON, missing
            required fields, wrong field types, or unrecognized enum values.
            Never returns a partial result or fail-safe sentinel.
    """
    text = _strip_fences(raw)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise VLMParseError("invalid JSON", raw) from None

    if not isinstance(data, dict):
        type_name = type(data).__name__
        raise VLMParseError(f"expected JSON object, got {type_name}", raw)

    for field in ("safe", "confidence", "reason", "patient_location"):
        if field not in data:
            raise VLMParseError(f"missing field: {field}", raw)

    # Validate safe
    safe_val = data["safe"]
    if type(safe_val) is not bool:
        got = type(safe_val).__name__
        raise VLMParseError(f"wrong type for safe: expected bool, got {got}", raw)

    # Validate confidence
    conf_val = data["confidence"]
    if not isinstance(conf_val, str):
        got = type(conf_val).__name__
        raise VLMParseError(f"wrong type for confidence: expected str, got {got}", raw)
    try:
        confidence = Confidence(conf_val.lower().strip())
    except ValueError:
        raise VLMParseError(f"unknown confidence value: {conf_val!r}", raw) from None

    # Validate reason
    reason_val = data["reason"]
    if not isinstance(reason_val, str):
        got = type(reason_val).__name__
        raise VLMParseError(f"wrong type for reason: expected str, got {got}", raw)
    if not reason_val.strip():
        raise VLMParseError("reason field is empty", raw)

    # Validate patient_location
    loc_val = data["patient_location"]
    if not isinstance(loc_val, str):
        got = type(loc_val).__name__
        raise VLMParseError(f"wrong type for patient_location: expected str, got {got}", raw)
    try:
        patient_location = PatientLocation(loc_val.lower().strip())
    except ValueError:
        raise VLMParseError(f"unknown patient_location value: {loc_val!r}", raw) from None

    # Validate sensor_notes (optional)
    sensor_notes_raw = data.get("sensor_notes")
    if sensor_notes_raw is None:
        sensor_notes = ""
    else:
        if not isinstance(sensor_notes_raw, str):
            got = type(sensor_notes_raw).__name__
            raise VLMParseError(f"wrong type for sensor_notes: expected str, got {got}", raw)
        sensor_notes = sensor_notes_raw

    return AssessmentResult(
        safe=safe_val,
        confidence=confidence,
        reason=reason_val,
        patient_location=patient_location,
        sensor_notes=sensor_notes,
    )
