"""Verify that stub implementations satisfy the Protocol contracts.

These tests don't test protocol logic (there is none). They confirm:
1. Stub implementations can be constructed and called.
2. Return types match what the Protocol promises.
3. The Protocol signatures match what the system actually needs.

If a Protocol signature changes, these stubs will break — which is intentional.
"""

from models import (
    Alert,
    AlertPriority,
    AlertType,
    AssessmentResult,
    Confidence,
    PatientLocation,
    SensorSnapshot,
)
from protocols import AlertChannel, SensorNode, VLMProvider


class StubVLMProvider:
    """Minimal VLMProvider stub. Returns a fixed safe assessment."""

    def assess(self, frame: bytes, prompt: str) -> AssessmentResult:
        return AssessmentResult(
            safe=True,
            confidence=Confidence.HIGH,
            reason="Stub: patient is resting.",
            patient_location=PatientLocation.IN_BED,
        )


class StubAlertChannel:
    """Minimal AlertChannel stub. Captures sent alerts for assertion."""

    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def send(self, alert: Alert) -> None:
        self.sent.append(alert)


class StubSensorNode:
    """Minimal SensorNode stub. Returns a Phase 1 snapshot."""

    def read(self) -> SensorSnapshot:
        return SensorSnapshot(load_cells_enabled=False, vitals_enabled=False)


def test_vlm_provider_assess_returns_assessment_result():
    provider: VLMProvider = StubVLMProvider()
    frame = b"\xff\xd8\xff"
    prompt = "Is the patient safe?"
    result = provider.assess(frame, prompt)
    assert isinstance(result, AssessmentResult)
    assert isinstance(result.safe, bool)
    assert isinstance(result.confidence, Confidence)
    assert isinstance(result.reason, str)
    assert isinstance(result.patient_location, PatientLocation)


def test_vlm_provider_accepts_empty_frame():
    provider: VLMProvider = StubVLMProvider()
    result = provider.assess(b"", "prompt")
    assert isinstance(result, AssessmentResult)


def test_alert_channel_send_captures_alert():
    channel: AlertChannel = StubAlertChannel()
    alert = Alert(
        alert_type=AlertType.UNSAFE_HIGH,
        priority=AlertPriority.HIGH,
        message="Grandma may be stuck.",
        url="http://grandma.local/gallery/1",
    )
    channel.send(alert)
    assert len(channel.sent) == 1  # type: ignore[attr-defined]
    assert channel.sent[0] == alert  # type: ignore[attr-defined]


def test_alert_channel_send_returns_none():
    channel: AlertChannel = StubAlertChannel()
    alert = Alert(
        alert_type=AlertType.SYSTEM,
        priority=AlertPriority.HIGH,
        message="Failover activated.",
    )
    result = channel.send(alert)
    assert result is None


def test_sensor_node_read_returns_snapshot():
    node: SensorNode = StubSensorNode()
    snapshot = node.read()
    assert isinstance(snapshot, SensorSnapshot)
    assert isinstance(snapshot.load_cells_enabled, bool)
    assert isinstance(snapshot.vitals_enabled, bool)


def test_sensor_node_phase1_snapshot_has_sensors_disabled():
    node: SensorNode = StubSensorNode()
    snapshot = node.read()
    assert snapshot.load_cells_enabled is False
    assert snapshot.vitals_enabled is False
