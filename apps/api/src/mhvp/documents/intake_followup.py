"""Follow-up proposals after an intake document was filed (master prompt 11.4, GA10-02).

After a person accepted an intake proposal, ``suggest`` derives per document type what should
happen next: invoice to the receipt inbox, damage photo to a ticket, contract to the contract
file, minutes to the meeting. The result is a list of **proposals** stored in
``AiProposal.final["followups"]`` with status ``proposed``; nothing is posted, approved or
created on its own. ``confirm`` (a second human step) only links the document to a ticket or
a contract; invoice and meeting stay hints for the existing receipt and meeting workflows."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import Document
from mhvp.tickets.models import Ticket, TicketStatus

INVOICE_RE = re.compile(r"\b(rechnung|rechnungsnummer|invoice)\b", re.I)
DAMAGE_RE = re.compile(r"(schaden|mangel|defekt|leck|wasserschaden|feuchtigkeit|schimmel)", re.I)
CONTRACT_RE = re.compile(r"(\bvertrag\b|mietvertrag|verwaltervertrag|dienstleistungsvertrag)", re.I)
MINUTES_RE = re.compile(r"(protokoll|beschlusssammlung|versammlung)", re.I)

# Kinds that confirm() may turn into a document link; the others stay hints.
LINKABLE_KINDS = {"ticket": "ticket", "contract_file": "contract"}


def _head(document: Document, category_name: str | None) -> str:
    return " ".join(p for p in (document.title, document.filename, category_name) if p)


async def suggest(
    session: AsyncSession,
    document: Document,
    *,
    category_name: str | None,
    text: str,
    final: dict[str, Any],
) -> list[dict[str, Any]]:
    """Follow-up proposals for one accepted document; empty when no type is recognised."""
    head = _head(document, category_name)
    sample = f"{head}\n{text[:5000]}"
    items: list[dict[str, Any]] = []

    def add(kind: str, label: str, **extra: Any) -> None:
        items.append({"kind": kind, "label": label, "status": "proposed", **extra})

    if INVOICE_RE.search(head) or (
        INVOICE_RE.search(sample) and (document.mime_type or "").startswith("application/pdf")
    ):
        add(
            "invoice",
            "Rechnung an den Belegeingang übergeben (Rechnungsdaten prüfen, dann Freigabe).",
            target_type="document",
            target_id=str(document.id),
        )
    if (document.mime_type or "").startswith("image/") and DAMAGE_RE.search(sample):
        ticket_id: str | None = None
        property_id = final.get("property_id")
        if property_id:
            ticket = await session.scalar(
                select(Ticket)
                .where(
                    Ticket.property_id == uuid.UUID(str(property_id)),
                    Ticket.status.in_(
                        [TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING]
                    ),
                )
                .order_by(Ticket.created_at.desc())
                .limit(1)
            )
            ticket_id = str(ticket.id) if ticket is not None else None
        if ticket_id:
            add(
                "ticket",
                "Schadensfoto an das offene Ticket des Objekts anhängen.",
                target_type="ticket",
                target_id=ticket_id,
            )
        else:
            add(
                "ticket_new",
                "Kein offenes Ticket gefunden: Ticket zum Schaden anlegen und Foto anhängen.",
            )
    if CONTRACT_RE.search(head):
        contract_id = final.get("contract_id")
        if contract_id:
            add(
                "contract_file",
                "Vertrag in der Vertragsakte ablegen.",
                target_type="contract",
                target_id=str(contract_id),
            )
        else:
            add("contract_file", "Vertrag einem Vertrag der Einheit zuordnen (Vertragsakte).")
    if MINUTES_RE.search(head):
        add("meeting", "Protokoll an die zugehörige Versammlung anhängen.")
    return items
