"""
AWS SNS SMS publisher with retry and message truncation.

Configuration (from env or boto3 default chain):
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
  SNS_PHONE_NUMBER  — E.164 format, e.g. +15551234567

SMS hard limit: 160 chars per segment; we truncate at 155 to leave room for "…".
"""
from __future__ import annotations

import logging
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

SMS_MAX_CHARS = 155  # leave 5 chars for ellipsis + safety margin
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # seconds


def _truncate(msg: str) -> str:
    if len(msg) <= SMS_MAX_CHARS:
        return msg
    return msg[: SMS_MAX_CHARS - 1] + "…"


def send_sms(
    message: str,
    phone_number: str | None = None,
    *,
    sns_client=None,
) -> bool:
    """
    Publish an SMS via AWS SNS.

    Parameters
    ----------
    message      : alert text (will be truncated if too long)
    phone_number : E.164 number (falls back to SNS_PHONE_NUMBER env var)
    sns_client   : optional pre-built boto3 SNS client (for testing/injection)

    Returns True on success, False on all retries exhausted.
    """
    target = phone_number or os.environ.get("SNS_PHONE_NUMBER", "")
    if not target:
        logger.error("SNS send failed: no phone number configured (set SNS_PHONE_NUMBER)")
        return False

    payload = _truncate(message)
    client = sns_client or boto3.client("sns")

    for attempt, delay in enumerate([0] + RETRY_BACKOFF, start=1):
        if delay:
            logger.info("SNS retry %d/%d after %ds", attempt, MAX_RETRIES, delay)
            time.sleep(delay)
        try:
            resp = client.publish(
                PhoneNumber=target,
                Message=payload,
                MessageAttributes={
                    "AWS.SNS.SMS.SMSType": {
                        "DataType": "String",
                        "StringValue": "Transactional",
                    }
                },
            )
            logger.info(
                "SNS SMS sent (MessageId=%s, attempt=%d)",
                resp.get("MessageId", "?"),
                attempt,
            )
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.warning("SNS publish failed (attempt %d): %s", attempt, exc)
            if attempt > MAX_RETRIES:
                logger.error("SNS: all retries exhausted for message: %s", payload[:60])
                return False

    return False


def send_health_alert(detail: str, phone_number: str | None = None, sns_client=None) -> bool:
    """Send a system health / degraded-mode SMS alert."""
    msg = f"[INVESTMENT MONITOR HEALTH ALERT] {detail}"
    return send_sms(msg, phone_number=phone_number, sns_client=sns_client)
