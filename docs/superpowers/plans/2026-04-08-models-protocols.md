# models.py and protocols.py Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `models.py` (domain enums + frozen dataclasses) and `protocols.py` (three Protocol interfaces) as the type foundation for grandma-watcher.

**Architecture:** Two dependency-free files. `models.py` imports nothing from the application — only stdlib. `protocols.py` imports from `models.py` only. All other modules depend on these two; nothing depends on them in return. No logic, no I/O, no configuration.

**Tech Stack:** Python 3.11+, stdlib only (`dataclasses`, `enum`, `typing`). Tests use `pytest`.

---

## Chunk 1: models.py and protocols.py

### Task 0: Bootstrap pytest configuration

The bare imports used throughout this plan (`from models import ...`, `from protocols import ...`) require pytest to resolve modules from the project root. This must be in place before any test can run — even to fail correctly.

**Files:**
- Create: `pyproject.toml`
- Create: `tests/` directory

- [ ] **Step 1: Create pyproject.toml**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
```

- [ ] **Step 2: Create the tests directory**

```bash
mkdir -p tests
```

- [ ] **Step 3: Verify pytest can be invoked with no errors (no tests yet)**

```bash
pytest tests/ -v
```

Expected: `no tests ran` — not an ImportError or configuration error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: bootstrap pytest config with project root pythonpath"
```

---

### Task 1: Write failing tests for models.py

**Files:**
- Create: `tests/test_models.py`

- [ ] **Step 1: Create the test file**

```python
# tests/test_models.py
import pytest
from models import (
    Confidence,
    PatientLocation,
    AlertType,
    AlertPriority,
    AssessmentResult,
    Alert,
    SensorSnapshot,
)


# --- Enum value tests ---

def test_confidence_values():
    assert Confidence.HIGH.value == "high"
    assert Confidence.MEDIUM.value == "medium"
    assert Confidence.LOW.value == "low"


def test_patient_location_values():
    assert PatientLocation.IN_BED.value == "in_bed"
    assert PatientLocation.BEING_ASSISTED_OUT.value == "being_assisted_out"
    assert PatientLocation.OUT_OF_BED.value == "out_of_bed"
    assert PatientLocation.UNKNOWN.value == "unknown"


def test_alert_type_values():
    assert AlertType.UNSAFE_HIGH.value == "unsafe_high"
    assert AlertType.UNSAFE_MEDIUM.value == "unsafe_medium"
    assert AlertType.SOFT_LOW_CONFIDENCE.value == "soft_low_confidence"
    assert AlertType.INFO.value == "info"
    assert AlertType.SYSTEM.value == "system"


def test_alert_priority_values():
    assert AlertPriority.NORMAL.value == "normal"
    assert AlertPriority.HIGH.value == "high"


# --- AssessmentResult dataclass tests ---

def test_assessment_result_construction():
    result = AssessmentResult(
        safe=True,
        confidence=Confidence.HIGH,
        reason="Patient resting in bed.",
        patient_location=PatientLocation.IN_BED,
    )
    assert result.safe is True
    assert result.confidence == Confidence.HIGH
    assert result.reason == "Patient resting in bed."
    assert result.patient_location == PatientLocation.IN_BED
    assert result.sensor_notes == ""  # default


def test_assessment_result_sensor_notes_explicit():
    result = AssessmentResult(
        safe=False,
        confidence=Confidence.MEDIUM,
        reason="Limb near rail.",
        patient_location=PatientLocation.IN_BED,
        sensor_notes="Weight shift detected on left load cells.",
    )
    assert result.sensor_notes == "Weight shift detected on left load cells."


def test_assessment_result_is_frozen():
    result = AssessmentResult(
        safe=True,
        confidence=Confidence.HIGH,
        reason="All clear.",
        patient_location=PatientLocation.IN_BED,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        result.safe = False  # type: ignore[misc]


# --- Alert dataclass tests ---

def test_alert_construction():
    alert = Alert(
        alert_type=AlertType.UNSAFE_HIGH,
        priority=AlertPriority.HIGH,
        message="Grandma may be stuck against the bed rail.",
        url="http://grandma.local/gallery/123",
    )
    assert alert.alert_type == AlertType.UNSAFE_HIGH
    assert alert.priority == AlertPriority.HIGH
    assert alert.message == "Grandma may be stuck against the bed rail."
    assert alert.url == "http://grandma.local/gallery/123"


def test_alert_url_defaults_to_empty_string():
    alert = Alert(
        alert_type=AlertType.SYSTEM,
        priority=AlertPriority.HIGH,
        message="API provider switched to fallback after 5 failures.",
    )
    assert alert.url == ""


def test_alert_is_frozen():
    alert = Alert(
        alert_type=AlertType.INFO,
        priority=AlertPriority.NORMAL,
        message="Grandma is back in bed — monitoring resumed.",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        alert.message = "different"  # type: ignore[misc]


# --- SensorSnapshot dataclass tests ---

def test_sensor_snapshot_construction():
    snapshot = SensorSnapshot(load_cells_enabled=False, vitals_enabled=False)
    assert snapshot.load_cells_enabled is False
    assert snapshot.vitals_enabled is False


def test_sensor_snapshot_phase2_enabled():
    snapshot = SensorSnapshot(load_cells_enabled=True, vitals_enabled=True)
    assert snapshot.load_cells_enabled is True
    assert snapshot.vitals_enabled is True


def test_sensor_snapshot_is_frozen():
    snapshot = SensorSnapshot(load_cells_enabled=False, vitals_enabled=False)
    with pytest.raises(Exception):  # FrozenInstanceError
        snapshot.load_cells_enabled = True  # type: ignore[misc]
```

- [ ] **Step 2: Run the tests and verify they fail with ImportError**

```bash
cd /Users/scottkostolni/programming_projects/grandma-watcher
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models'`

---

### Task 2: Implement models.py

**Files:**
- Create: `models.py`

- [ ] **Step 1: Write models.py**

```python
# models.py
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
```

- [ ] **Step 2: Run the models tests and verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 3: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add domain types in models.py with full test coverage"
```

---

### Task 3: Write failing tests for protocols.py

**Files:**
- Create: `tests/test_protocols.py`

- [ ] **Step 1: Write the test file**

The goal here is not to test the Protocol definitions themselves (they have no logic), but to verify that stub implementations written against the Protocol signatures actually satisfy them. If a stub is structurally wrong, `mypy` catches it. At the pytest level, these tests verify that stubs are callable and return the correct types.

```python
# tests/test_protocols.py
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


# --- Stubs ---

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


# --- VLMProvider tests ---

def test_vlm_provider_assess_returns_assessment_result():
    provider: VLMProvider = StubVLMProvider()
    frame = b"\xff\xd8\xff"  # JPEG magic bytes
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


# --- AlertChannel tests ---

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


# --- SensorNode tests ---

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
```

- [ ] **Step 2: Run and verify ImportError on protocols**

```bash
pytest tests/test_protocols.py -v
```

Expected: `ModuleNotFoundError: No module named 'protocols'`

---

### Task 4: Implement protocols.py

**Files:**
- Create: `protocols.py`

- [ ] **Step 1: Write protocols.py**

```python
# protocols.py
"""Stable extension-point interfaces for grandma-watcher.

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
```

- [ ] **Step 2: Run the protocol tests and verify they pass**

```bash
pytest tests/test_protocols.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all 18 tests pass (12 from test_models.py, 6 from test_protocols.py).

- [ ] **Step 4: Run the linter and formatter**

```bash
ruff check models.py protocols.py tests/test_models.py tests/test_protocols.py
black --check models.py protocols.py tests/test_models.py tests/test_protocols.py
```

Expected: zero warnings from ruff, zero reformatting needed from black. If black reports reformatting needed, run `black models.py protocols.py tests/test_models.py tests/test_protocols.py` then re-check.

- [ ] **Step 5: Commit**

```bash
git add protocols.py tests/test_protocols.py
git commit -m "feat: add Protocol interfaces in protocols.py with stub-based tests"
```

---

## Done

Both files implemented, tested, and committed. The type foundation is in place for all subsequent Prep tasks:
- `config.yaml` schema (next task) will reference `SensorSnapshot` for the sensor snapshot shape
- `alert.py` will import `AssessmentResult`, `Alert`, `AlertType`, `AlertPriority`, `AlertChannel`
- `monitor.py` will import `VLMProvider`, `AssessmentResult`, `SensorSnapshot`
- `prompt_builder.py` will import `SensorSnapshot`
- `dataset.py` will import `AssessmentResult`, `SensorSnapshot`
