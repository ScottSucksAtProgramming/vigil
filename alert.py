"""Alert decision logic for grandma-watcher.

Single public function: decide_alert_type().
Pure function — no I/O, no logging, no global state.
Dependencies: models.py, config.py only.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from enum import Enum

import requests

from config import AlertsConfig
from models import (
    Alert,
    AlertPriority,
    AlertType,
    AssessmentResult,
    Confidence,
    PatientLocation,
)


class SilenceEvent(Enum):
    """Event returned by PatientLocationStateMachine.push() when silence state changes."""

    ACTIVATE = "activate"
    RESUME = "resume"


def decide_alert_type(
    assessment: AssessmentResult,
    *,
    medium_unsafe_in_window: int,
    low_unsafe_in_window: int,
    silence_active: bool,
    medium_cooldown_active: bool,
    low_cooldown_active: bool,
    config: AlertsConfig,
) -> AlertType | None:
    """Determine which alert type to fire, or None if no alert should fire.

    Rules evaluated in strict order; first match wins.
    HIGH confidence bypasses all suppression (silence and cooldown).
    MEDIUM and LOW suppressed by silence_active or respective cooldowns.
    MEDIUM and LOW fire only when window count meets or exceeds configured threshold.
    Raises ValueError for any Confidence value not explicitly handled.
    """
    # Rule 1: safe — short-circuit before any confidence check
    if assessment.safe:
        return None

    # Rule 2: HIGH — bypasses silence and cooldown
    if assessment.confidence == Confidence.HIGH:
        return AlertType.UNSAFE_HIGH

    # Rule 3: MEDIUM — suppressed by silence or medium cooldown; fires at threshold
    if assessment.confidence == Confidence.MEDIUM:
        if silence_active:
            return None
        if medium_cooldown_active:
            return None
        if medium_unsafe_in_window >= config.medium_unsafe_window_threshold:
            return AlertType.UNSAFE_MEDIUM
        return None

    # Rule 4: LOW — suppressed by silence or low cooldown; fires at threshold
    if assessment.confidence == Confidence.LOW:
        if silence_active:
            return None
        if low_cooldown_active:
            return None
        if low_unsafe_in_window >= config.low_unsafe_window_threshold:
            return AlertType.SOFT_LOW_CONFIDENCE
        return None

    # Defensive fallthrough — unexpected or future Confidence value
    raise ValueError(f"Unexpected confidence value: {assessment.confidence!r}")


class SlidingWindowCounter:
    """Rolling N-frame window tracking medium and low confidence unsafe counts.

    Each push appends the assessment's Confidence (if unsafe) or None (if safe).
    safe=True always appends None regardless of the confidence field value.
    Old entries age out automatically via deque(maxlen=N).
    """

    def __init__(self, window_size: int) -> None:
        self._window: deque[Confidence | None] = deque(maxlen=window_size)

    def push(self, assessment: AssessmentResult) -> None:
        """Append this assessment to the window."""
        if assessment.safe:
            self._window.append(None)
        else:
            self._window.append(assessment.confidence)

    def medium_count(self) -> int:
        """Return how many of the last N frames were MEDIUM confidence unsafe."""
        return sum(1 for c in self._window if c == Confidence.MEDIUM)

    def low_count(self) -> int:
        """Return how many of the last N frames were LOW confidence unsafe."""
        return sum(1 for c in self._window if c == Confidence.LOW)

    def flush(self) -> None:
        """Clear all window entries (called on silence activation)."""
        self._window.clear()


class CooldownTimer:
    """Tracks whether a cooldown period is active for a given alert type.

    clock is injectable for testability. Production code uses time.monotonic.

    start() is idempotent: if the cooldown is already active, calling
    start() again does nothing. It does NOT extend the expiry.

    cancel() is used on silence activation to abandon the active cooldown.
    """

    def __init__(
        self,
        duration_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._duration = duration_seconds
        self._clock = clock
        self._expires_at: float | None = None

    @property
    def active(self) -> bool:
        """True if a cooldown is running and has not yet expired."""
        if self._expires_at is None:
            return False
        return self._clock() < self._expires_at

    def start(self) -> None:
        """Start the cooldown. No-op if already active."""
        if self.active:
            return
        self._expires_at = self._clock() + self._duration

    def cancel(self) -> None:
        """Cancel the active cooldown (used on silence activation)."""
        self._expires_at = None


class PatientLocationStateMachine:
    """Pure state machine for auto-silence activation and resume by patient location."""

    def __init__(
        self,
        *,
        out_of_bed_frames_to_silence: int,
        in_bed_frames_to_resume: int,
    ) -> None:
        if out_of_bed_frames_to_silence < 1:
            raise ValueError("out_of_bed_frames_to_silence must be >= 1")
        if in_bed_frames_to_resume < 1:
            raise ValueError("in_bed_frames_to_resume must be >= 1")
        self._out_of_bed_threshold = out_of_bed_frames_to_silence
        self._in_bed_threshold = in_bed_frames_to_resume
        self._consecutive_out_of_bed = 0
        self._consecutive_in_bed = 0
        self._auto_silenced = False

    @property
    def auto_silenced(self) -> bool:
        """True when auto-silence is currently active."""
        return self._auto_silenced

    def push(self, assessment: AssessmentResult) -> SilenceEvent | None:
        """Process one frame. Returns a SilenceEvent if silence state changes, else None."""
        location = assessment.patient_location

        if location == PatientLocation.OUT_OF_BED:
            self._consecutive_out_of_bed += 1
            self._consecutive_in_bed = 0
        elif location in (
            PatientLocation.IN_BED,
            PatientLocation.UNKNOWN,
        ):
            self._consecutive_out_of_bed = 0
            self._consecutive_in_bed += 1
        elif location == PatientLocation.BEING_ASSISTED_OUT:
            self._consecutive_out_of_bed = 0
            self._consecutive_in_bed = 0
        else:
            raise ValueError(f"Unexpected PatientLocation: {location!r}")
        if not self._auto_silenced and self._consecutive_out_of_bed >= self._out_of_bed_threshold:
            self._auto_silenced = True
            self._consecutive_out_of_bed = 0
            return SilenceEvent.ACTIVATE
        if self._auto_silenced and self._consecutive_in_bed >= self._in_bed_threshold:
            self._auto_silenced = False
            self._consecutive_in_bed = 0
            return SilenceEvent.RESUME
        return None


_PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

_ALERT_TITLES: dict[AlertType, str] = {
    AlertType.UNSAFE_HIGH: "Grandma — Immediate Attention Needed",
    AlertType.UNSAFE_MEDIUM: "Grandma Alert",
    AlertType.SOFT_LOW_CONFIDENCE: "Grandma — Please Check",
    AlertType.INFO: "Grandma — Info",
    AlertType.SYSTEM: "System Alert",
}


class PushoverChannel:
    """Delivers alerts to a single Pushover user via the Pushover HTTP API.

    Satisfies AlertChannel structurally — no import from protocols.py needed.
    Injectable: construct one instance per recipient (Mom, builder, etc.).

    Raises on delivery failure (4xx/5xx HTTP). Does not swallow errors.
    """

    def __init__(
        self,
        *,
        api_key: str,
        user_key: str,
        high_priority: int = 1,
        emergency_retry_seconds: int = 60,
        emergency_expire_seconds: int = 3600,
    ) -> None:
        self._api_key = api_key
        self._user_key = user_key
        self._high_priority = high_priority
        self._emergency_retry_seconds = emergency_retry_seconds
        self._emergency_expire_seconds = emergency_expire_seconds
        self._session = requests.Session()

    def send(self, alert: Alert) -> None:
        """Send alert via Pushover HTTP API. Raises on delivery failure."""
        priority = self._high_priority if alert.priority == AlertPriority.HIGH else 0
        title = _ALERT_TITLES.get(alert.alert_type, "Grandma Alert")

        payload: dict[str, str | int] = {
            "token": self._api_key,
            "user": self._user_key,
            "message": alert.message,
            "title": title,
            "priority": priority,
        }

        if alert.url:
            payload["url"] = alert.url

        if priority == 2:
            payload["retry"] = self._emergency_retry_seconds
            payload["expire"] = self._emergency_expire_seconds

        response = self._session.post(_PUSHOVER_API_URL, data=payload)
        response.raise_for_status()
