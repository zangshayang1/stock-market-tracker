"""Unit tests for SNS alert publisher using moto mock."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from market_tracker.alerts.sns import _truncate, send_sms, send_health_alert

SMS_MAX = 155


class TestTruncate:
    def test_short_message_unchanged(self):
        msg = "hello"
        assert _truncate(msg) == msg

    def test_long_message_truncated(self):
        msg = "A" * 200
        result = _truncate(msg)
        assert len(result) <= SMS_MAX + 1  # +1 for ellipsis char
        assert result.endswith("…")

    def test_exact_limit_unchanged(self):
        msg = "B" * SMS_MAX
        assert _truncate(msg) == msg


class TestSendSMS:
    def test_success(self):
        mock_client = MagicMock()
        mock_client.publish.return_value = {"MessageId": "test-id"}

        with patch.dict(os.environ, {"SNS_PHONE_NUMBER": "+15551234567"}):
            ok = send_sms("Test alert", sns_client=mock_client)

        assert ok
        mock_client.publish.assert_called_once()
        call_kwargs = mock_client.publish.call_args[1]
        assert call_kwargs["PhoneNumber"] == "+15551234567"
        assert call_kwargs["Message"] == "Test alert"

    def test_no_phone_number_fails(self):
        mock_client = MagicMock()
        env = {k: v for k, v in os.environ.items() if k != "SNS_PHONE_NUMBER"}
        with patch.dict(os.environ, env, clear=True):
            ok = send_sms("Test", sns_client=mock_client)
        assert not ok
        mock_client.publish.assert_not_called()

    def test_explicit_phone_overrides_env(self):
        mock_client = MagicMock()
        mock_client.publish.return_value = {"MessageId": "x"}
        ok = send_sms("Test", phone_number="+19998887777", sns_client=mock_client)
        assert ok
        assert mock_client.publish.call_args[1]["PhoneNumber"] == "+19998887777"

    def test_retry_on_failure_exhausts(self):
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.publish.side_effect = ClientError(
            {"Error": {"Code": "500", "Message": "oops"}}, "Publish"
        )
        with patch("market_tracker.alerts.sns.time.sleep"):
            ok = send_sms("Test", phone_number="+15551234567", sns_client=mock_client)
        assert not ok
        assert mock_client.publish.call_count == 4  # 1 initial + 3 retries

    def test_message_truncated_before_send(self):
        mock_client = MagicMock()
        mock_client.publish.return_value = {"MessageId": "y"}
        long_msg = "X" * 300
        send_sms(long_msg, phone_number="+15551234567", sns_client=mock_client)
        sent_msg = mock_client.publish.call_args[1]["Message"]
        assert len(sent_msg) <= SMS_MAX + 1


class TestSendHealthAlert:
    def test_prefixes_message(self):
        mock_client = MagicMock()
        mock_client.publish.return_value = {"MessageId": "z"}
        send_health_alert("disk full", phone_number="+15551234567", sns_client=mock_client)
        sent = mock_client.publish.call_args[1]["Message"]
        assert "[INVESTMENT MONITOR HEALTH ALERT]" in sent
        assert "disk full" in sent
