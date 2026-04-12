"""Stable extension-point interfaces for vigil.

These three Protocols are the architectural seams of the system. New VLM providers,
alert channels, and sensor nodes are added by implementing one of these Protocols —
existing code is never modified.

Dependency rule: this module imports from models.py only.
"""

from typing import Protocol

from models import Alert, AssessmentResult, SensorSnapshot


class VLMProvider(Protocol):
    """A VLM provider that can assess a camera frame for patient safety.

    assess() is synchronous and blocking. The 30-second monitoring cycle budget
    accommodates blocking I/O. An async variant would be a Protocol-level change
    and must go through the stop-and-flag process before implementation.
    """

    def assess(self, frame: bytes, prompt: str) -> AssessmentResult:
        """Assess a JPEG frame and return a validated safety result.

        Args:
            frame: Raw JPEG bytes from the go2rtc snapshot endpoint.
            prompt: Fully-built prompt string from prompt_builder.py.

        Returns:
            AssessmentResult with safe, confidence, reason, and patient_location.

        Raises:
            On network failure, timeout, or API error. The caller catches and retries.
        """
        ...


class AlertChannel(Protocol):
    """A channel that can deliver an alert to a caregiver or the builder.

    send() raises on delivery failure. The caller is responsible for catching
    exceptions. AlertChannel implementations must not swallow errors silently.
    """

    def send(self, alert: Alert) -> None:
        """Deliver an alert via this channel.

        Args:
            alert: The alert payload to deliver.

        Raises:
            On delivery failure (network error, auth error, etc.).
            Does not swallow errors — the caller handles retries or fallback.
        """
        ...


class SensorNode(Protocol):
    """A sensor node that can return a snapshot of current readings."""

    def read(self) -> SensorSnapshot:
        """Poll the sensor node and return the current snapshot.

        Returns:
            SensorSnapshot reflecting the current enabled/disabled state and readings.

        Raises:
            On HTTP failure or timeout. The caller handles graceful degradation.
        """
        ...
