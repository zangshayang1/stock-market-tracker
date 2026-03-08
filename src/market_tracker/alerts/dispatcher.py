"""
Alert dispatcher — routes to SMS or email based on NotifyConfig.
"""
from __future__ import annotations

import logging

from market_tracker.models import NotifyConfig

logger = logging.getLogger(__name__)


def send_alert(message: str, notify: NotifyConfig) -> bool:
    """Send an alert via the configured delivery channel.

    Target address/number is read from env vars:
      email → SMTP_USER
      sms   → SNS_PHONE_NUMBER
    """
    if notify.delivery == "email":
        import os
        to_address = os.environ.get("SMTP_USER", "")
        if not to_address:
            logger.error("Delivery is 'email' but SMTP_USER env var is not set")
            return False
        from market_tracker.alerts.email_alert import send_email
        return send_email(message, to_address)
    else:
        from market_tracker.alerts.sns import send_sms
        return send_sms(message)
