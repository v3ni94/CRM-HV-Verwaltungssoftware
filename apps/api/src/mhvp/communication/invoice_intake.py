"""Automatischer Belegeingang (M14-05), standardmäßig aus.

Ist der Mandantenschalter ``tenant_settings.invoice_intake_auto`` gesetzt, startet der
Gmail-Abruf für jede neu angelegte eingehende Nachricht und jeden PDF-Anhang, der nach der
folgenden Heuristik wie eine Rechnung aussieht, genau einen ``extract_invoice``-Lauf über
``mhvp.ai.routers.create_extraction_run`` (derselbe Weg wie "Als Rechnung erfassen"; Stufen,
Budget- und Freigabeprüfungen des Gateways bleiben unverändert). Ergebnis ist wie bisher nur ein
Vorschlag zur Prüfung, gebucht wird nichts (Regel 0.1.6).

Heuristik (``looks_like_invoice``), bewusst einfach und ohne KI:

* Betreff enthält ``Rechnung``, ``Invoice`` oder ``Beleg`` (Groß- und Kleinschreibung egal), oder
* Absenderadresse enthält im lokalen Teil ``rechnung``, ``invoice`` oder ``billing``
  (z. B. ``rechnung@firma.de``), oder
* Dateiname des Anhangs enthält ``Rechnung`` oder ``Invoice`` (Groß- und Kleinschreibung egal)
  oder ``RE-`` in Großbuchstaben am Anfang oder nach einem Trennzeichen (``RE-2026-001.pdf``,
  ``Scan_RE-4711.pdf``; ``Pre-Order.pdf`` zählt nicht).

Zusätzlich muss der Anhang ein PDF sein (``mime_type == application/pdf``).

Idempotenz: vor dem Start wird je Anhang eine Zeile in ``invoice_intake_auto_run`` mit
eindeutigem Schlüssel (tenant_id, document_id) per ``INSERT ... ON CONFLICT DO NOTHING``
beansprucht. Nur wer die Zeile anlegt, startet den Lauf; ein erneuter Abruf, ein Retry oder ein
paralleler Worker erzeugt keinen zweiten Lauf.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

TRIGGER = "invoice_intake_auto"
PDF = "application/pdf"
_SUBJECT = re.compile(r"rechnung|invoice|beleg", re.IGNORECASE)
_SENDER_LOCAL = re.compile(r"rechnung|invoice|billing", re.IGNORECASE)
_FILENAME = re.compile(r"rechnung|invoice", re.IGNORECASE)
_FILENAME_RE = re.compile(r"(?:^|[\s_.\-(\[])RE-")


def looks_like_invoice(subject: str | None, from_address: str | None, filename: str | None) -> bool:
    """Heuristik aus dem Moduldocstring; reine Funktion ohne Datenbankzugriff."""
    if subject and _SUBJECT.search(subject):
        return True
    if from_address:
        address = from_address.rsplit("<", 1)[-1]
        local = address.split("@", 1)[0]
        if _SENDER_LOCAL.search(local):
            return True
    return bool(filename and (_FILENAME.search(filename) or _FILENAME_RE.search(filename)))


@dataclass(frozen=True)
class Attachment:
    message_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    mime_type: str


@dataclass(frozen=True)
class MailInfo:
    message_id: uuid.UUID
    subject: str | None
    from_address: str | None
    direction: str


def candidates(
    mails: Iterable[MailInfo],
    attachments: Iterable[Attachment],
    already_claimed: set[uuid.UUID],
) -> list[Attachment]:
    """Anhänge, für die ein Lauf gestartet werden soll: eingehend, PDF, Heuristik erfüllt, noch
    nicht beansprucht und je Dokument nur einmal (auch wenn mehrere Mails denselben Anhang
    tragen)."""
    by_id = {m.message_id: m for m in mails}
    seen = set(already_claimed)
    out: list[Attachment] = []
    for att in attachments:
        mail = by_id.get(att.message_id)
        if mail is None or mail.direction != "in" or att.mime_type != PDF:
            continue
        if att.document_id in seen:
            continue
        if not looks_like_invoice(mail.subject, mail.from_address, att.filename):
            continue
        seen.add(att.document_id)
        out.append(att)
    return out


async def enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    return bool(await session.scalar(select(TenantSettings.invoice_intake_auto)))


async def claim(session: AsyncSession, tenant_id: uuid.UUID, att: Attachment) -> uuid.UUID | None:
    """Beansprucht den Anhang; gibt die Markierungs-ID zurück oder None, wenn schon vorhanden."""
    from mhvp.communication.models import InvoiceIntakeAutoRun

    marker_id = uuid.uuid4()
    stmt = (
        insert(InvoiceIntakeAutoRun)
        .values(
            id=marker_id,
            tenant_id=tenant_id,
            document_id=att.document_id,
            message_id=att.message_id,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "document_id"])
        .returning(InvoiceIntakeAutoRun.id)
    )
    marker: uuid.UUID | None = await session.scalar(stmt)
    return marker


async def intake_for_messages(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    message_ids: list[uuid.UUID],
    actor_user_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Legt für die neuen Nachrichten die Läufe an (Status queued) und gibt deren IDs zurück.
    Der Aufrufer stößt die Ausführung nach dem Commit an. Bei ausgeschaltetem Schalter
    passiert nichts."""
    if not message_ids or not await enabled(session):
        return []
    from mhvp.ai.models import AiTask
    from mhvp.ai.routers import create_extraction_run
    from mhvp.communication.models import InvoiceIntakeAutoRun, Message
    from mhvp.documents.models import Document

    messages = list(await session.scalars(select(Message).where(Message.id.in_(message_ids))))
    mails = [MailInfo(m.id, m.subject, m.from_address, m.direction) for m in messages]
    doc_ids = {d for m in messages for d in (m.attachment_document_ids or [])}
    if not doc_ids:
        return []
    docs = {
        d.id: d for d in await session.scalars(select(Document).where(Document.id.in_(doc_ids)))
    }
    attachments = [
        Attachment(m.id, d, docs[d].filename, docs[d].mime_type)
        for m in messages
        for d in (m.attachment_document_ids or [])
        if d in docs
    ]
    claimed = set(
        await session.scalars(
            select(InvoiceIntakeAutoRun.document_id).where(
                InvoiceIntakeAutoRun.document_id.in_(doc_ids)
            )
        )
    )
    run_ids: list[uuid.UUID] = []
    for att in candidates(mails, attachments, claimed):
        marker_id = await claim(session, tenant_id, att)
        if marker_id is None:
            continue
        run_id = await create_extraction_run(
            session,
            tenant_id,
            actor_user_id,
            AiTask.EXTRACT_INVOICE,
            [att.document_id],
            "Rechnung aus E-Mail-Anhang erfassen (automatischer Belegeingang)",
            "invoice",
            att.message_id,
            trigger=TRIGGER,
        )
        marker = await session.get(InvoiceIntakeAutoRun, marker_id)
        if marker is not None:
            marker.task_run_id = run_id
        run_ids.append(run_id)
    if run_ids:
        await session.flush()
        log.info("invoice intake auto runs created", extra={"count": len(run_ids)})
    return run_ids
