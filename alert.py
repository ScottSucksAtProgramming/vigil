"""Alert decision logic for grandma-watcher.

Single public function: decide_alert_type().
Pure function — no I/O, no logging, no global state.
Dependencies: models.py, config.py only.
"""

from __future__ import annotations

from config import AlertsConfig
from models import AlertType, AssessmentResult, Confidence


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
