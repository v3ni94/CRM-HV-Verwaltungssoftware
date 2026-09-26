"""Shared mail transport of a mailbox: Gmail ``send_raw`` (OAuth refresh token) or SMTP with
STARTTLS. Used by the four-eyes dispatch (``routers.approve``) and by system mails without an
approval step (SLA escalation, M35). Errors are raised as ``MailTransportError`` with a text
that never contains the mailbox secret."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings

SMTP_TIMEOUT = 30


class MailTransportError(RuntimeError):
    """Sending failed or no usable transport is configured."""


class MailTransportUncertainError(MailTransportError):
    """The transport did not answer (network error, timeout): the mail may or may not have
    left. The caller keeps the send attempt open and verifies by Message-ID (M1)."""


def is_sendable(box: Mailbox | None) -> bool:
    return box is not None and box.enabled and bool(box.secret)


async def send_message(
    session: AsyncSession, settings: Settings, box: Mailbox, msg: EmailMessage
) -> str | None:
    """Sends ``msg`` through ``box``; returns the Gmail message id (``None`` for SMTP)."""
    from mhvp.communication import gmail

    if not is_sendable(box):
        raise MailTransportError("Kein eingerichtetes Postfach für den Versand (M20-01).")
    if box.kind == "gmail":
        try:
            client_id, client_secret = await gmail.oauth_client(session, settings)
            client = gmail.make_client(client_id, client_secret, box)
            try:
                return await client.send_raw(bytes(msg))
            finally:
                await client.aclose()
        except gmail.GmailError as exc:
            raise MailTransportError(str(exc)) from exc
        except httpx.HTTPError as exc:
            # Netzfehler vor oder nach dem Versand: der Aufrufer behandelt den Versand als
            # nicht nachgewiesen (Review 26.09.2026, M1, Abgleich per Message-ID).
            raise MailTransportUncertainError(
                f"Gmail nicht erreichbar: {type(exc).__name__}"
            ) from exc
    if not box.smtp_host:
        raise MailTransportError("Kein eingerichtetes Postfach für den Versand (M20-01).")
    try:
        with smtplib.SMTP(box.smtp_host, box.smtp_port or 587, timeout=SMTP_TIMEOUT) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(box.username or box.address, box.secret or "")
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailTransportError(f"SMTP-Versand fehlgeschlagen: {type(exc).__name__}") from exc
    return None
