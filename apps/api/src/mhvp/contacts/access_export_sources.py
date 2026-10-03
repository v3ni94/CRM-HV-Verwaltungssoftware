"""Further data sources and processing log of the access export (GAM-402, GAM-403, 7.11 S06).

GAM-402: every table with a foreign key on ``contact.id`` is classified here, so the export is
complete per source. A source is either

* ``COVERED``: already part of the base export (contact child tables, consents, parties,
  tickets, messages, portal account), or
* in ``FURTHER_SOURCES`` with an explicit field allowlist and one of the existing tenant
  switches (``include_*``, off by default, AC07-01): switch off means only the number of rows
  is listed under ``withheld.further_sources_count``, switch on lists the allowlisted fields, or
* ``EXCLUDED`` with the reason why the rows are not data of the subject.

The guard test ``tests/unit/test_ap14_access_export_sources.py`` fails when a new foreign key
on ``contact.id`` is in none of the three lists.

GAM-403: the processing log also lists events of the entities that belong to the person
(tickets, messages, consents, bank accounts, portal account, further sources) and events whose
payload names the contact, with type and time only; ``audit_log`` entries of those entities
with the names of the changed fields (never the values). Transfers to recipients (service
providers, webhooks, claims adjuster, Lexware) are a separate rubric ``recipients``: events
with ``payload.recipient`` and ``payload.contact_id`` of the person.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import AuditLog, DomainEvent


@dataclass(frozen=True)
class Source:
    key: str
    table: str
    column: str
    switch: str
    fields: tuple[str, ...]
    label: str
    where: str = ""  # constant SQL fragment (never user input)


FURTHER_SOURCES: tuple[Source, ...] = (
    # Communication (include_communication)
    Source(
        "call_log",
        "call_log",
        "contact_id",
        "include_communication",
        ("event", "direction", "number", "started_at", "duration_seconds"),
        "Anrufprotokoll",
    ),
    Source(
        "dispatch",
        "dispatch",
        "contact_id",
        "include_communication",
        ("channel", "status", "evidence_kind", "sent_at", "delivered_at"),
        "Versand",
    ),
    Source(
        "postal_job",
        "postal_job",
        "contact_id",
        "include_communication",
        ("provider", "status", "recipient_address", "pages", "submitted_at", "completed_at"),
        "Briefversand über Dienstleister",
    ),
    Source(
        "appointment_proposed",
        "work_order_appointment_proposal",
        "proposed_by_contact_id",
        "include_communication",
        ("starts_at", "note", "status", "decided_at"),
        "Terminvorschläge (eigene)",
    ),
    Source(
        "appointment_decided",
        "work_order_appointment_proposal",
        "decided_by_contact_id",
        "include_communication",
        ("starts_at", "status", "decided_at"),
        "Terminvorschläge (entschieden)",
    ),
    Source(
        "invoice_copy_requester",
        "lexoffice_invoice_copy_request",
        "requester_contact_id",
        "include_communication",
        ("invoice_number", "status", "created_at"),
        "Rechnungskopie angefordert",
    ),
    Source(
        "invoice_copy_recipient",
        "lexoffice_invoice_copy_request",
        "recipient_contact_id",
        "include_communication",
        ("invoice_number", "status", "created_at"),
        "Rechnungskopie empfangen",
    ),
    # Tickets (include_tickets)
    Source(
        "ticket_comments",
        "ticket_comment",
        "author_contact_id",
        "include_tickets",
        ("body", "created_at"),
        "Eigene Ticketkommentare",
        "internal = false",
    ),
    Source(
        "board_votes",
        "ticket_board_vote",
        "contact_id",
        "include_tickets",
        ("vote", "comment", "source", "created_at"),
        "Beiratsvoten",
    ),
    Source(
        "work_order_ratings",
        "work_order_rating",
        "rated_by_contact_id",
        "include_tickets",
        ("party", "stars", "comment", "created_at"),
        "Bewertungen von Aufträgen",
    ),
    Source(
        "migrated_tickets",
        "migrated_ticket",
        "contact_id",
        "include_tickets",
        ("source", "title", "status_text", "created_on", "closed_on"),
        "Übernommene Vorgänge",
    ),
    Source(
        "work_orders",
        "work_order",
        "provider_contact_id",
        "include_tickets",
        ("description", "status", "scheduled_at", "created_at"),
        "Aufträge als Dienstleister",
    ),
    # Documents (include_documents)
    Source(
        "generated_documents",
        "generated_document",
        "recipient_contact_id",
        "include_documents",
        ("template_code", "context_type", "created_at"),
        "Erzeugte Schreiben",
    ),
    # Portal (include_portal_account)
    Source(
        "portal_representation",
        "portal_representation",
        "principal_contact_id",
        "include_portal_account",
        ("valid_from", "valid_to", "status", "revoked_at"),
        "Vertretungen im Portal",
    ),
    Source(
        "board_access",
        "board_access",
        "contact_id",
        "include_portal_account",
        ("created_at", "revoked_at"),
        "Beiratszugang",
    ),
    # Contracts, roles and relations (include_contracts)
    Source(
        "prospect",
        "prospect",
        "contact_id",
        "include_contracts",
        ("status", "viewing_at", "source", "delete_after", "created_at"),
        "Interessent",
    ),
    Source(
        "handover_participant",
        "handover_participant",
        "contact_id",
        "include_contracts",
        (
            "role",
            "salutation",
            "first_name",
            "last_name",
            "company",
            "street",
            "house_number",
            "postal_code",
            "city",
            "email",
            "phone",
            "captured_at",
        ),
        "Teilnahme an Übergaben",
    ),
    Source(
        "meeting_proxy",
        "meeting_attendance",
        "proxy_contact_id",
        "include_contracts",
        ("present", "online", "portal_confirmed_at"),
        "Vollmacht in Versammlungen",
    ),
    Source(
        "property_contact",
        "property_contact",
        "contact_id",
        "include_contracts",
        ("category_code", "valid_from", "valid_to"),
        "Objektansprechpartner",
    ),
    Source(
        "property_owner_tax_advisor",
        "property_owner",
        "tax_advisor_contact_id",
        "include_contracts",
        ("valid_from", "valid_to"),
        "Steuerberater eines Eigentümers",
    ),
    Source(
        "service_provider_relation",
        "service_provider_relation",
        "contact_id",
        "include_contracts",
        ("contract_type_code", "valid_from", "valid_to", "customer_number"),
        "Dienstleisterbeziehung",
    ),
    Source(
        "service_contract",
        "service_contract",
        "provider_contact_id",
        "include_contracts",
        ("title", "starts_at", "ends_at", "cancelled_at"),
        "Dienstleistungsverträge",
    ),
    Source(
        "property_creditor",
        "property_creditor",
        "contact_id",
        "include_contracts",
        ("trade", "since", "source"),
        "Kreditor eines Objekts",
    ),
    Source(
        "termination_successor_manager",
        "property_termination",
        "successor_manager_contact_id",
        "include_contracts",
        ("notice_date", "effective_date"),
        "Nachfolgeverwaltung",
    ),
    Source(
        "termination_successor_owner",
        "property_termination",
        "successor_owner_contact_id",
        "include_contracts",
        ("notice_date", "effective_date"),
        "Nachfolgeeigentümer",
    ),
    Source(
        "objektakte_assignment",
        "objektakte_party_assignment",
        "contact_id",
        "include_contracts",
        ("role", "valid_from", "valid_to", "share"),
        "Zuordnung in der Objektakte",
    ),
    Source(
        "metering_billing_recipient",
        "metering_unit_assignment",
        "billing_recipient_contact_id",
        "include_contracts",
        ("valid_from", "valid_to", "occupancy_status"),
        "Empfänger Heizkostenabrechnung",
    ),
    Source(
        "metering_consumption_recipient",
        "metering_unit_assignment",
        "consumption_info_recipient_contact_id",
        "include_contracts",
        ("valid_from", "valid_to", "occupancy_status"),
        "Empfänger Verbrauchsinformation",
    ),
    Source(
        "hoa_inspection_request",
        "hoa_inspection_request",
        "applicant_contact_id",
        "include_contracts",
        ("requested_on", "scope_text", "status", "released_at"),
        "Einsichtnahme in Verwaltungsunterlagen",
    ),
    Source(
        "admin_fee_manager",
        "admin_fee_setting",
        "manager_contact_id",
        "include_contracts",
        ("start_date", "end_date"),
        "Verwaltervergütung (Verwalter)",
    ),
    Source(
        "supplier_tax_profile",
        "supplier_tax_profile",
        "contact_id",
        "include_contracts",
        ("construction_services", "reverse_charge", "exemption_valid_from", "exemption_valid_to"),
        "Steuerprofil Lieferant",
    ),
    Source(
        "provider_availability",
        "provider_availability",
        "provider_contact_id",
        "include_contracts",
        ("starts_at", "ends_at", "kind"),
        "Verfügbarkeit Dienstleister",
    ),
    Source(
        "membership",
        "membership",
        "contact_id",
        "include_contracts",
        ("status", "position", "phone", "mobile_phone", "created_at"),
        "Mitarbeiterkonto",
    ),
    # Payments (include_payments)
    Source(
        "bank_account_changes",
        "contact_bank_account_change",
        "contact_id",
        "include_payments",
        ("kind", "valid_to", "status", "decided_at", "created_at"),
        "Änderungshistorie Bankverbindung",
    ),
    Source(
        "direct_debit_orders",
        "direct_debit_order",
        "contact_id",
        "include_payments",
        ("mandate_reference", "sequence_type", "amount", "due_date", "bank_status", "returned_on"),
        "Lastschriften",
    ),
    Source(
        "sepa_mandate_proposals",
        "portal_sepa_mandate_proposal",
        "contact_id",
        "include_payments",
        ("reference", "scheme", "iban", "bic", "status", "confirmed_at", "decided_at"),
        "SEPA-Mandatsvorschläge",
    ),
    Source(
        "migrated_open_items",
        "migrated_open_item",
        "contact_id",
        "include_payments",
        (
            "kind",
            "original_due_date",
            "original_amount",
            "paid_amount",
            "open_amount",
            "description",
        ),
        "Übernommene offene Posten",
    ),
    Source(
        "rent_invoices",
        "rent_invoice",
        "contact_id",
        "include_payments",
        ("number", "invoice_date", "period_start", "period_end", "gross_total", "status"),
        "Mietrechnungen",
    ),
    Source(
        "provider_invoices",
        "invoice",
        "provider_contact_id",
        "include_payments",
        ("number", "invoice_date", "gross", "review_status"),
        "Eingangsrechnungen",
    ),
    Source(
        "recurring_invoice_plans",
        "recurring_invoice_plan",
        "provider_contact_id",
        "include_payments",
        ("gross", "interval_months", "start_date", "end_date"),
        "Wiederkehrende Rechnungen",
    ),
    Source(
        "ledger_accounts",
        "ledger_account",
        "contact_id",
        "include_payments",
        ("number", "name"),
        "Personenkonten",
    ),
    Source(
        "heating_cost_imports",
        "heating_cost_import",
        "provider_contact_id",
        "include_payments",
        ("provider_name", "period_from", "period_to"),
        "Heizkostenimporte als Abrechnungsdienst",
    ),
    Source(
        "lexoffice_contact_link",
        "lexoffice_contact_link",
        "contact_id",
        "include_payments",
        ("customer_number", "vendor_number", "sync_status", "last_synced_at"),
        "Übermittlung an Lexware Office (Kontakt)",
    ),
    Source(
        "lexoffice_invoice_drafts",
        "lexoffice_invoice_draft",
        "contact_id",
        "include_payments",
        ("invoice_kind", "status", "created_at"),
        "Rechnungsentwürfe in Lexware Office",
    ),
    Source(
        "lexoffice_recurring_prep",
        "lexoffice_recurring_prep",
        "contact_id",
        "include_payments",
        ("status", "done_at"),
        "Serienrechnungen Lexware Office",
    ),
)

# Already part of the base export or of the AK06/GAI-506 sources.
COVERED: frozenset[tuple[str, str]] = frozenset(
    {
        ("consent", "contact_id"),
        ("party_member", "contact_id"),
        ("portal_account", "contact_id"),
        ("ticket", "contact_id"),
        ("ticket", "initiator_contact_id"),
        ("message", "contact_id"),
    }
)
# Tables starting with ``contact_`` are the contact's own child tables (base export), except
# those listed in FURTHER_SOURCES or EXCLUDED.
EXCLUDED: dict[tuple[str, str], str] = {
    ("contact_relation", "related_contact_id"): (
        "Beziehung aus Sicht der anderen Person; die eigene Sicht steht unter relations."
    ),
    (
        "contact_bank_account",
        "bank_contact_id",
    ): "Verweis auf das Kreditinstitut, nicht die Person.",
    ("contact_merge", "source_id"): "Interner Bereinigungsvorgang, Ergebnis im Kontakt.",
    ("contact_merge", "target_id"): "Interner Bereinigungsvorgang, Ergebnis im Kontakt.",
    ("privacy_access_request", "contact_id"): "Auskunftsvorgang selbst (Protokoll im Export).",
    ("privacy_erasure_request", "contact_id"): "Löschvorgang, eigenes Verfahren.",
    ("immoware_dav_contact", "matched_contact_id"): (
        "Importspiegel des Altsystems; Inhalt entspricht den Kontaktstammdaten."
    ),
}


LOG_EXCLUDED_ENTITY_TYPES: tuple[str, ...] = (
    "contact_access_export",
    "privacy_access_request",
)


def classified() -> set[tuple[str, str]]:
    return {(s.table, s.column) for s in FURTHER_SOURCES} | set(COVERED) | set(EXCLUDED)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "value") and not isinstance(value, str | int | float | bool):
        return value.value
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


async def _present_tables(session: AsyncSession, names: set[str]) -> set[str]:
    rows = await session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ANY(:n)"
        ),
        {"n": sorted(names)},
    )
    return {str(r[0]) for r in rows.all()}


def _has_created_at(table: str) -> bool:
    from mhvp.core.db.base import Base

    t = Base.metadata.tables.get(table)
    return t is not None and "created_at" in t.columns


async def add_further_sources(
    session: AsyncSession,
    contact_id: uuid.UUID,
    generated_at: datetime,
    options: Any,
    content: dict[str, Any],
) -> list[tuple[str, uuid.UUID]]:
    """Adds ``further_sources`` (switch on) or counts (switch off). Returns ``(table, id)`` of
    all rows found, for the processing log (GAM-403)."""
    present = await _present_tables(session, {s.table for s in FURTHER_SOURCES})
    out: dict[str, Any] = {}
    counts: dict[str, int] = {}
    found: list[tuple[str, uuid.UUID]] = []
    for src in FURTHER_SOURCES:
        if src.table not in present:
            continue
        cond = [f'"{src.column}" = :cid']
        if _has_created_at(src.table):
            cond.append("created_at <= :g")
        if src.where:
            cond.append(src.where)
        where = " AND ".join(cond)
        order = "created_at, id" if _has_created_at(src.table) else "id"
        cols = ", ".join(f'"{c}"' for c in ("id", *src.fields))
        rows = (
            await session.execute(
                text(f'SELECT {cols} FROM "{src.table}" WHERE {where} ORDER BY {order}'),  # noqa: S608
                {"cid": contact_id, "g": generated_at},
            )
        ).all()
        found.extend((src.table, r[0]) for r in rows)
        if not rows:
            continue
        if getattr(options, src.switch, False):
            out[src.key] = {
                "label": src.label,
                "rows": [
                    {f: _jsonable(v) for f, v in zip(src.fields, r[1:], strict=True)} for r in rows
                ],
            }
        else:
            counts[src.key] = len(rows)
    if out:
        content["further_sources"] = out
    if counts:
        content["withheld"]["further_sources_count"] = counts
    return found


async def add_unlinked_messages(
    session: AsyncSession,
    contact_id: uuid.UUID,
    generated_at: datetime,
    options: Any,
    content: dict[str, Any],
    fields: tuple[str, ...],
) -> list[uuid.UUID]:
    """Messages from an address of the contact without ``contact_id`` (GAM-402)."""
    from mhvp.communication.models import Message
    from mhvp.contacts.models import ContactEmail

    emails = [
        str(e).strip().lower()
        for e in (
            await session.scalars(
                select(ContactEmail.email).where(ContactEmail.contact_id == contact_id)
            )
        ).all()
        if e
    ]
    if not emails:
        return []
    where = and_(
        Message.contact_id.is_(None),
        func.lower(Message.from_address).in_(emails),
        Message.created_at <= generated_at,
    )
    rows = (
        await session.scalars(select(Message).where(where).order_by(Message.created_at, Message.id))
    ).all()
    if not rows:
        return []
    if options.include_communication:
        content["communication_by_address"] = [
            {f: _jsonable(getattr(m, f, None)) for f in fields} for m in rows
        ]
    else:
        content["withheld"]["communication_by_address_count"] = len(rows)
    return [m.id for m in rows]


async def related_entity_ids(session: AsyncSession, contact_id: uuid.UUID) -> set[uuid.UUID]:
    """Ids of the base export entities that belong to the person (GAM-403)."""
    from mhvp.communication.models import Message
    from mhvp.contacts.models import Consent, ContactBankAccount
    from mhvp.portal.models import PortalAccount
    from mhvp.tickets.models import Ticket

    ids: set[uuid.UUID] = {contact_id}
    for stmt in (
        select(Ticket.id).where(
            or_(Ticket.contact_id == contact_id, Ticket.initiator_contact_id == contact_id)
        ),
        select(Message.id).where(Message.contact_id == contact_id),
        select(Consent.id).where(Consent.contact_id == contact_id),
        select(ContactBankAccount.id).where(ContactBankAccount.contact_id == contact_id),
        select(PortalAccount.id).where(PortalAccount.contact_id == contact_id),
    ):
        ids |= set((await session.scalars(stmt)).all())
    return ids


async def processing_log(
    session: AsyncSession,
    contact_id: uuid.UUID,
    generated_at: datetime,
    entity_ids: set[uuid.UUID],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """``(log, audit, recipients)``: events (type, entity type, time), field changes (names
    only) and transfers to recipients of the person up to ``generated_at``."""
    cid = str(contact_id)
    events = (
        await session.scalars(
            select(DomainEvent)
            .where(
                DomainEvent.occurred_at <= generated_at,
                # The export's own workflow (prepare, review, release, download) and access
                # requests are emitted next to the build; they would change the reviewed hash.
                DomainEvent.entity_type.notin_(LOG_EXCLUDED_ENTITY_TYPES),
                or_(
                    and_(DomainEvent.entity_type == "contact", DomainEvent.entity_id == contact_id),
                    DomainEvent.entity_id.in_(entity_ids),
                    DomainEvent.payload["contact_id"].astext == cid,
                ),
            )
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        )
    ).all()
    log: list[dict[str, Any]] = []
    recipients: list[dict[str, Any]] = []
    for e in events:
        entry = {"type": e.type, "occurred_at": e.occurred_at.isoformat()}
        if e.entity_type != "contact":
            entry["entity_type"] = e.entity_type
        log.append(entry)
        payload = e.payload or {}
        if payload.get("recipient") and str(payload.get("contact_id") or "") == cid:
            recipients.append(
                {
                    "recipient": str(payload["recipient"]),
                    "type": e.type,
                    "basis": payload.get("sharing_basis"),
                    "occurred_at": e.occurred_at.isoformat(),
                }
            )
    audits = (
        await session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_id.in_(entity_ids), AuditLog.occurred_at <= generated_at)
            .order_by(AuditLog.occurred_at, AuditLog.id)
        )
    ).all()
    audit = [
        {
            "entity_type": a.entity_type,
            "occurred_at": a.occurred_at.isoformat(),
            "changed_fields": sorted(str(k) for k in (a.changes or {})),
        }
        for a in audits
    ]
    return log, audit, recipients
