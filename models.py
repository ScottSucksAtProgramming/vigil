"""Domain types for grandma-watcher.

This module contains all enums and dataclasses exchanged between components.
It has no imports from the application and no logic — only data shapes.
"""

from dataclasses import dataclass
from enum import Enum


class Confidence(Enum):
    """VLM response confidence level. Values match the JSON response schema."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PatientLocation(Enum):
    """VLM-reported patient location. Values match the JSON response schema."""

    IN_BED = "in_bed"
    BEING_ASSISTED_OUT = "being_assisted_out"
    OUT_OF_BED = "out_of_bed"
    UNKNOWN = "unknown"


class AlertType(Enum):
    """Category of alert being sent. Determines routing and logging behavior."""

    UNSAFE_HIGH = "unsafe_high"
    UNSAFE_MEDIUM = "unsafe_medium"
    SOFT_LOW_CONFIDENCE = "soft_low_confidence"
    INFO = "info"
    SYSTEM = "system"


class AlertPriority(Enum):
    """Urgency of the alert. AlertChannel implementations act on this independently of AlertType."""

    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True)
class AssessmentResult:
    """Validated output of a single VLM safety assessment.

    Constructed by monitor.py after parsing and validating the VLM JSON response.
    Invalid or missing fields never reach this type — the parser handles them first.
    """

    safe: bool
    confidence: Confidence
    reason: str
    patient_location: PatientLocation
    sensor_notes: str = ""


@dataclass(frozen=True)
class Alert:
    """Payload delivered to an AlertChannel.

    url defaults to "" for SYSTEM and INFO alerts that have no dashboard link.
    AlertChannel implementations treat "" as "omit the link".
    """

    alert_type: AlertType
    priority: AlertPriority
    message: str
    url: str = ""


@dataclass(frozen=True)
class SensorSnapshot:
    """Snapshot of sensor node availability at a monitoring cycle.

    Phase 1: both fields are always False (sensors not yet deployed).
    Phase 2: extend with additional fields — all new fields must have defaults
    to preserve backward compatibility with existing construction sites.
    """

    load_cells_enabled: bool
    vitals_enabled: bool
