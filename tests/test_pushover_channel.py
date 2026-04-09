"""Tests for PushoverChannel in alert.py — mocked HTTP, no network calls."""

from unittest.mock import Mock, patch

import pytest
import requests.exceptions

from alert import PushoverChannel
from models import Alert, AlertPriority, AlertType


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
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)
    return mock_resp


def test_pushover_channel_constructs_with_kwargs():
    ch = _make_channel()
    assert ch._api_key == "test-app-key"
    assert ch._user_key == "test-user-key"
    assert ch._high_priority == 1


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


def test_send_high_priority_alert_uses_configured_priority():
    ch = _make_channel(high_priority=1)
    with patch("alert.requests.Session.post", return_value=_make_mock_response()) as mock_post:
        ch.send(_make_alert(priority=AlertPriority.HIGH))
    payload = mock_post.call_args[1]["data"]
    assert payload["priority"] == 1


def test_send_high_priority_respects_configured_value():
    ch = _make_channel(
        high_priority=2,
        emergency_retry_seconds=30,
        emergency_expire_seconds=600,
    )
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


def test_send_priority_2_includes_retry_and_expire():
    ch = _make_channel(
        high_priority=2,
        emergency_retry_seconds=45,
        emergency_expire_seconds=900,
    )
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


def test_send_raises_on_http_error():
    ch = _make_channel()
    with patch("alert.requests.Session.post", return_value=_make_mock_response(ok=False)):
        with pytest.raises(requests.exceptions.HTTPError):
            ch.send(_make_alert())
