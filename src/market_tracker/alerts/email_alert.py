"""
SMTP email alert sender.

Configuration (from env):
  SMTP_HOST      — default: smtp.gmail.com
  SMTP_PORT      — default: 587 (STARTTLS)
  SMTP_USER      — sending Gmail address
  SMTP_PASSWORD  — Gmail app password (not your account password)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))


def send_email(message: str, to_address: str) -> bool:
    """
    Send an alert email via SMTP.

    Parameters
    ----------
    message    : alert body text
    to_address : recipient email address

    Returns True on success, False on failure.
    """
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")

    if not smtp_user or not smtp_password:
        logger.error("Email send failed: SMTP_USER or SMTP_PASSWORD not set")
        return False

    subject = message.splitlines()[0][:80]
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_address

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_address, msg.as_string())
        logger.info("Email alert sent to %s", to_address)
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False
