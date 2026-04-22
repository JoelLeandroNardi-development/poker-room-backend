from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import quote

from . import config

class EmailDeliveryError(RuntimeError):
    pass

class PasswordResetEmailSender(Protocol):
    async def send_password_reset(self, *, email: str, reset_url: str) -> None:
        ...

def build_password_reset_url(token: str) -> str:
    separator = "&" if "?" in config.PASSWORD_RESET_BASE_URL else "?"
    return f"{config.PASSWORD_RESET_BASE_URL}{separator}token={quote(token)}"

class ConfiguredPasswordResetEmailSender:
    async def send_password_reset(self, *, email: str, reset_url: str) -> None:
        backend = config.PASSWORD_RESET_EMAIL_BACKEND

        if backend == "disabled":
            return
        if backend == "console":
            print(f"Password reset link for {email}: {reset_url}")
            return
        if backend == "smtp":
            await asyncio.to_thread(self._send_smtp, email=email, reset_url=reset_url)
            return

        raise EmailDeliveryError(f"Unsupported password reset email backend: {backend}")

    def _send_smtp(self, *, email: str, reset_url: str) -> None:
        if not config.SMTP_HOST:
            raise EmailDeliveryError("SMTP_HOST is required for SMTP password reset email")

        message = EmailMessage()
        message["From"] = config.SMTP_FROM_EMAIL
        message["To"] = email
        message["Subject"] = "Reset your poker room password"
        message.set_content(
            "A password reset was requested for your poker room account.\n\n"
            f"Use this link to reset your password:\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        )

        try:
            with smtplib.SMTP(
                config.SMTP_HOST,
                config.SMTP_PORT,
                timeout=config.SMTP_TIMEOUT_SECONDS,
            ) as smtp:
                if config.SMTP_USE_TLS:
                    smtp.starttls()
                if config.SMTP_USERNAME and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Unable to send password reset email") from exc