# PushoverChannel Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `PushoverChannel` class in `alert.py` and add three Pushover priority config fields to `AlertsConfig`, with full test coverage.

**Architecture:** `PushoverChannel` is an `AlertChannel` implementation (satisfies the Protocol structurally). It wraps the Pushover HTTP API using `requests` directly (consistent with `OpenRouterProvider`). It is injectable: callers construct one instance per recipient (Mom, builder) passing `api_key` and `user_key` explicitly. Priority for `AlertPriority.HIGH` alerts is configurable via `AlertsConfig.high_alert_pushover_priority` (default 1). If priority is 2 (emergency), Pushover requires `retry` and `expire` params — these are also configurable.

**Files to modify:**
- `config.py` — add `high_alert_pushover_priority`, `pushover_emergency_retry_seconds`, `pushover_emergency_expire_seconds` to `AlertsConfig`
- `alert.py` — add `import requests`, expand models import, add `_PUSHOVER_API_URL` constant, `_ALERT_TITLES` dict, `PushoverChannel` class
- `tests/fixtures/config_valid.yaml` — add the 3 new fields to `alerts:` section

**Files to create:**
- `tests/test_pushover_channel.py`

---

## Chunk 1: Config — add Pushover priority fields

**Files:**
- Modify: `config.py`
- Modify: `tests/fixtures/config_valid.yaml`
- Modify: `tests/test_config.py`

### Task 1: Add fields to AlertsConfig

- [ ] **Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
def test_alerts_config_has_high_alert_pushover_priority(sample_config):
    assert sample_config.alerts.high_alert_pushover_priority == 1

def test_alerts_config_has_emergency_retry_and_expire(sample_config):
    assert sample_config.alerts.pushover_emergency_retry_seconds == 60
    assert sample_config.alerts.pushover_emergency_expire_seconds == 3600
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_config.py -v -k "high_alert_pushover_priority or emergency"`
Expected: FAIL — `AttributeError: 'AlertsConfig' object has no attribute 'high_alert_pushover_priority'`

- [ ] **Step 3: Add fields to AlertsConfig in config.py**

In `AlertsConfig`, after `low_confidence_cooldown_minutes`, add:

```python
    high_alert_pushover_priority: int = 1
    pushover_emergency_retry_seconds: int = 60
    pushover_emergency_expire_seconds: int = 3600
```

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_config.py -v -k "high_alert_pushover_priority or emergency"`
Expected: PASS

- [ ] **Step 5: Update the fixture YAML**

In `tests/fixtures/config_valid.yaml`, in the `alerts:` section, add:

```yaml
  high_alert_pushover_priority: 1
  pushover_emergency_retry_seconds: 60
  pushover_emergency_expire_seconds: 3600
```

- [ ] **Step 6: Run full test suite and lint**

Run: `pytest && ruff check config.py && black --check config.py`
Expected: all pass, no warnings

- [ ] **Step 7: Commit**

```bash
git add config.py tests/fixtures/config_valid.yaml tests/test_config.py
git commit -m "feat: add Pushover priority config fields to AlertsConfig"
```

---

## Chunk 2: PushoverChannel — implementation and tests

**Files:**
- Modify: `alert.py`
- Create: `tests/test_pushover_channel.py`

---

### Task 2: PushoverChannel skeleton (constructor only)

- [ ] **Step 1: Write failing test**

Create `tests/test_pushover_channel.py`:

```python
"""Tests for PushoverChannel in alert.py — mocked HTTP, no network calls."""

from unittest.mock import Mock, patch

import pytest
import requests.exceptions

from alert import PushoverChannel
from models import Alert, AlertPriority, AlertType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_alert(
    alert_type: AlertType = AlertType.UNSAFE_HIGH,
    priority: AlertPriority = AlertPriority.HIGH,
    message: str = "Test alert.",
    url: str = "",
) -> Alert:
    return Alert(alert_type=alert_type, priority=priority, message=message, url=url)


def _make_channel(
    *,
    api_key: str = "test-app-key",
    user_key: str = "test-user-key",
    high_priority: int = 1,
    emergency_retry_seconds: int = 60,
    emergency_expire_seconds: int = 3600,
) -> PushoverChannel:
    return PushoverChannel(
        api_key=api_key,
        user_key=user_key,
        high_priority=high_priority,
        emergency_retry_seconds=emergency_retry_seconds,
        emergency_expire_seconds=emergency_expire_seconds,
    )


def _make_mock_response(*, ok: bool = True) -> Mock:
    mock_resp = Mock()
    if ok:
        mock_resp.raise_for_status = Mock()
    else:
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_resp
        )
    return mock_resp


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_pushover_channel_constructs_with_kwargs():
    ch = _make_channel()
    assert ch._api_key == "test-app-key"
    assert ch._user_key == "test-user-key"
    assert ch._high_priority == 1
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_pushover_channel.py -v`
Expected: FAIL — `ImportError: cannot import name 'PushoverChannel' from 'alert'`

- [ ] **Step 3: Add imports and skeleton to alert.py**

At the top of `alert.py`, add `import requests` after the existing stdlib imports (`import time`).

Update the models import from:
```python
from models import AlertType, AssessmentResult, Confidence, PatientLocation
```
to:
```python
from models import Alert, AlertPriority, AlertType, AssessmentResult, Confidence, PatientLocation
```

Append after the `PatientLocationStateMachine` class:

```python
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
        return None  # stub
```

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_pushover_channel.py::test_pushover_channel_constructs_with_kwargs -v`
Expected: PASS

---

### Task 3: Write all remaining tests (RED)

Add all of the following tests to `tests/test_pushover_channel.py` before any implementation is changed. All of these should fail because `send()` is still a stub.

- [ ] **Step 1: Add all tests**

```python
# ---------------------------------------------------------------------------
# POST URL and required payload fields
# ---------------------------------------------------------------------------


def test_send_posts_to_pushover_url():
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert())
    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "https://api.pushover.net/1/messages.json"


def test_send_payload_contains_required_fields():
    ch = _make_channel(api_key="app123", user_key="user456")
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(message="Help!"))
    payload = mock_post.call_args[1]["data"]
    assert payload["token"] == "app123"
    assert payload["user"] == "user456"
    assert payload["message"] == "Help!"
    assert "title" in payload
    assert "priority" in payload


# ---------------------------------------------------------------------------
# Priority mapping
# ---------------------------------------------------------------------------


def test_send_high_priority_alert_uses_configured_priority():
    ch = _make_channel(high_priority=1)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.HIGH))
    payload = mock_post.call_args[1]["data"]
    assert payload["priority"] == 1


def test_send_high_priority_respects_configured_value():
    ch = _make_channel(high_priority=2, emergency_retry_seconds=30, emergency_expire_seconds=600)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.HIGH))
    payload = mock_post.call_args[1]["data"]
    assert payload["priority"] == 2


def test_send_normal_priority_alert_uses_zero():
    ch = _make_channel(high_priority=1)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.NORMAL))
    payload = mock_post.call_args[1]["data"]
    assert payload["priority"] == 0


# ---------------------------------------------------------------------------
# URL inclusion / omission
# ---------------------------------------------------------------------------


def test_send_includes_url_when_non_empty():
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(url="http://example.com/dashboard"))
    payload = mock_post.call_args[1]["data"]
    assert payload["url"] == "http://example.com/dashboard"


def test_send_omits_url_when_empty():
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(url=""))
    payload = mock_post.call_args[1]["data"]
    assert "url" not in payload


# ---------------------------------------------------------------------------
# Title mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alert_type,expected_title",
    [
        (AlertType.UNSAFE_HIGH, "Grandma — Immediate Attention Needed"),
        (AlertType.UNSAFE_MEDIUM, "Grandma Alert"),
        (AlertType.SOFT_LOW_CONFIDENCE, "Grandma — Please Check"),
        (AlertType.INFO, "Grandma — Info"),
        (AlertType.SYSTEM, "System Alert"),
    ],
)
def test_send_title_by_alert_type(alert_type, expected_title):
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(alert_type=alert_type))
    payload = mock_post.call_args[1]["data"]
    assert payload["title"] == expected_title


# ---------------------------------------------------------------------------
# Emergency priority params (priority == 2)
# ---------------------------------------------------------------------------


def test_send_priority_2_includes_retry_and_expire():
    ch = _make_channel(high_priority=2, emergency_retry_seconds=45, emergency_expire_seconds=900)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.HIGH))
    payload = mock_post.call_args[1]["data"]
    assert payload["retry"] == 45
    assert payload["expire"] == 900


def test_send_priority_1_omits_retry_and_expire():
    ch = _make_channel(high_priority=1)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.HIGH))
    payload = mock_post.call_args[1]["data"]
    assert "retry" not in payload
    assert "expire" not in payload


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_send_raises_on_http_error():
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response(ok=False)):
        with pytest.raises(requests.exceptions.HTTPError):
            ch.send(_make_alert())
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/test_pushover_channel.py -v`
Expected: `test_pushover_channel_constructs_with_kwargs` PASSES; all others FAIL (stub `send()` returns None without posting)

---

### Task 4: Implement send() and verify GREEN

- [ ] **Step 1: Replace the stub send() with full implementation**

In `alert.py`, replace the stub `send()` body:

```python
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
```

- [ ] **Step 2: Verify GREEN**

Run: `pytest tests/test_pushover_channel.py -v`
Expected: all tests PASS

---

### Task 5: Final verification and commit

- [ ] **Step 1: Run full test suite and lint**

Run: `pytest && ruff check alert.py && black --check alert.py`
Expected: all pass, no warnings

- [ ] **Step 2: Mark task done in todo.taskpaper**

In `todo.taskpaper`, change:
```
- Implement PushoverChannel satisfying AlertChannel protocol @na
```
to:
```
- Implement PushoverChannel satisfying AlertChannel protocol @done
```

- [ ] **Step 3: Commit**

```bash
git add alert.py tests/test_pushover_channel.py todo.taskpaper
git commit -m "feat: implement PushoverChannel in alert.py (Milestone 1)"
```

---

## Acceptance Criteria

- [ ] All tests in `tests/test_pushover_channel.py` pass
- [ ] `pytest` (full suite) exits 0 — no regressions
- [ ] `ruff check alert.py` and `black --check alert.py` pass
- [ ] `PushoverChannel` is importable from `alert`
- [ ] `todo.taskpaper`: task marked `@done`
