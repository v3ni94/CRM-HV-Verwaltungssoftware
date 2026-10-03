"""Data subject access export with review before release (AC07, GA08-06, 7.11 S06).

The export is built from an explicit field allowlist per entity; everything not listed is left
out (hashes such as ``iban_fingerprint``, tokens, internal notes, external ids, AI raw data,
event payloads). References to other persons are reduced to the role, never their name or id
("Fremdpersonenprüfung"). Whether withheld categories (for example internal notes) must be
disclosed after all is a legal question (OPEN_QUESTIONS AC07-01); the reviewer sees the list
of withheld categories and decides outside the system.

AE33 (AC07-01): two tenant switches (``contact_access_export_setting``) widen the scope after
a legal decision. ``third_party_scope`` ``none`` (default) keeps other persons at their role,
``names`` adds their name and role (never addresses, contact data, identifiers or bank data);
``include_internal_notes`` (default off) adds the free text note and the contact notes without
author. The values in force at preparation are frozen into the prepared event, so the review,
the release and every download rebuild exactly the content that was reviewed, whatever the
switches say later. The decision stays open (OPEN_QUESTIONS AC07-01).

Workflow, journaled as append only domain events (no own table, migration 0340 is a noop):

``prepared`` (``contacts:export``) -> ``reviewed`` (``contacts:approve``, not the preparer)
-> ``released`` (``contacts:approve``, not the preparer) -> ``downloaded`` (any number of
times, each logged). ``rejected`` ends the export. The prepared event stores only the content
hash and the generation time, never the content; the download rebuilds the export with the
same generation time and must reproduce the reviewed hash, otherwise the data changed and the
export has to be prepared again.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import (
    Consent,
    Contact,
    ContactAccessExportSetting,
    ContactBankAccount,
    ContactNote,
    ContactRelation,
    Party,
    PartyMember,
)
from mhvp.core.events import DomainEvent, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.redaction import is_secret_key

ENTITY_TYPE = "contact_access_export"
EVENT_PREPARED = "contact.access_export.prepared"
EVENT_REVIEWED = "contact.access_export.reviewed"
EVENT_RELEASED = "contact.access_export.released"
EVENT_REJECTED = "contact.access_export.rejected"
EVENT_DOWNLOADED = "contact.access_export.downloaded"

STATUS_PREPARED = "prepared"
STATUS_REVIEWED = "reviewed"
STATUS_RELEASED = "released"
STATUS_REJECTED = "rejected"
_STATUS_BY_EVENT = {
    EVENT_PREPARED: STATUS_PREPARED,
    EVENT_REVIEWED: STATUS_REVIEWED,
    EVENT_RELEASED: STATUS_RELEASED,
    EVENT_REJECTED: STATUS_REJECTED,
}

# Allowlists per entity (AC07). A field is exported only when it is named here.
CONTACT_FIELDS: tuple[str, ...] = (
    "kind",
    "display_name",
    "salutation",
    "letter_salutation",
    "title",
    "first_name",
    "last_name",
    "company_name",
    "legal_form",
    "position",
    "date_of_birth",
    "language",
    "preferred_channel",
    "is_consumer",
    "blocked",
    "blocked_at",
    "types",
    "roles",
    "tags",
    "created_at",
    "updated_at",
)
ADDRESS_FIELDS = (
    "label",
    "street",
    "house_number",
    "addition",
    "postal_code",
    "city",
    "state",
    "country",
    "is_primary",
)
PHONE_FIELDS = ("label", "number", "is_primary")
EMAIL_FIELDS = ("label", "email", "is_primary", "is_portal_login")
IDENTIFIER_FIELDS = ("kind", "value")
DATE_FIELDS = ("kind", "date", "note")
BANK_FIELDS = (
    "iban",
    "bic",
    "bank_name",
    "valid_from",
    "valid_to",
    "sepa_enabled",
    "mandate_reference",
    "mandate_signed_on",
)
CONSENT_FIELDS = (
    "kind",
    "granted_at",
    "revoked_at",
    "source",
    "record_type",
    "text_version",
    "client_evidence_recorded",
)
NOTE_FIELDS = ("category", "title", "body", "created_at", "follow_up_on")
THIRD_PARTY_PLACEHOLDER = "Dritte Person (Angaben zurückgehalten)"
SCOPE_NONE = "none"
SCOPE_NAMES = "names"
THIRD_PARTY_SCOPES = (SCOPE_NONE, SCOPE_NAMES)


@dataclass(frozen=True)
class ExportOptions:
    """Scope of one export, frozen at preparation (AE33). The defaults are the conservative
    variant that was the only one before the switches existed."""

    third_party_scope: str = SCOPE_NONE
    include_internal_notes: bool = False
    # GAI-506: further data sources, tenant switches in ``tenant_settings.sources``
    # (``SCOPE_SOURCES_KEY``); off by default, the extent is AC07-01.
    include_tickets: bool = False
    include_communication: bool = False
    include_documents: bool = False
    # AK06 (GAI-506): portal account with login events and sessions, payment data (open items
    # of the contracts) and contract data; tenant switches, off by default (AC07-01).
    include_portal_account: bool = False
    include_payments: bool = False
    include_contracts: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "third_party_scope": self.third_party_scope,
            "include_internal_notes": self.include_internal_notes,
            "include_tickets": self.include_tickets,
            "include_communication": self.include_communication,
            "include_documents": self.include_documents,
            "include_portal_account": self.include_portal_account,
            "include_payments": self.include_payments,
            "include_contracts": self.include_contracts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExportOptions:
        if not raw:
            return cls()
        scope = str(raw.get("third_party_scope", SCOPE_NONE))
        return cls(
            third_party_scope=scope if scope in THIRD_PARTY_SCOPES else SCOPE_NONE,
            include_internal_notes=bool(raw.get("include_internal_notes", False)),
            include_tickets=bool(raw.get("include_tickets", False)),
            include_communication=bool(raw.get("include_communication", False)),
            include_documents=bool(raw.get("include_documents", False)),
            include_portal_account=bool(raw.get("include_portal_account", False)),
            include_payments=bool(raw.get("include_payments", False)),
            include_contracts=bool(raw.get("include_contracts", False)),
        )


SCOPE_SOURCES_KEY = "access_export_sources"
SOURCE_SWITCHES = (
    "include_tickets",
    "include_communication",
    "include_documents",
    "include_portal_account",
    "include_payments",
    "include_contracts",
)


async def source_switches(session: AsyncSession) -> dict[str, bool]:
    """Switches of the further data sources (GAI-506) from the tenant settings JSON."""
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings))
    raw = ((row.sources or {}) if row else {}).get(SCOPE_SOURCES_KEY) or {}
    return {k: bool(raw.get(k, False)) for k in SOURCE_SWITCHES}


async def current_options(session: AsyncSession) -> ExportOptions:
    """Switches of the tenant; no row means the conservative defaults."""
    row = await session.scalar(select(ContactAccessExportSetting))
    sources = await source_switches(session)
    if row is None:
        return ExportOptions.from_dict(sources)
    return ExportOptions.from_dict(
        {
            "third_party_scope": row.third_party_scope,
            "include_internal_notes": row.include_internal_notes,
            **sources,
        }
    )


# Categories that are not part of the export by default; the reviewer sees them listed. With
# the tenant switches (AE33) the released categories drop out of the list (``withheld_for``).
WITHHELD = {
    "internal_notes": "Interne Vermerke (Kontaktnotizen und Notizfeld) werden nicht "
    "automatisch ausgegeben; Herausgabe nur nach Einzelprüfung (AC07-01).",
    "secrets": "Hashwerte, Fingerabdrücke, Tokens und Zugangsdaten werden nie ausgegeben.",
    "external_ids": "Interne Fremdsystem-Kennungen werden nicht ausgegeben.",
    "ai_raw_data": "KI-Rohdaten (Eingaben, Ausgaben, Vorschläge) werden nicht ausgegeben.",
    "third_parties": "Angaben zu anderen Personen werden nur mit Rolle, ohne Namen und "
    "Kennung ausgegeben.",
    "event_payloads": "Das Verarbeitungsprotokoll nennt nur Art und Zeitpunkt.",
}
# GAI-506: sources that are only listed (with count) until the tenant switch includes them.
WITHHELD_SOURCES = {
    "include_tickets": (
        "tickets",
        "Vorgänge (Tickets) des Kontakts werden nur gezählt, nicht ausgegeben "
        "(Mandantenschalter, AC07-01).",
    ),
    "include_communication": (
        "communication",
        "Nachrichten (E-Mail, Messenger, Brief) des Kontakts werden nur gezählt, nicht "
        "ausgegeben (Mandantenschalter, AC07-01).",
    ),
    "include_documents": (
        "documents",
        "Dem Kontakt zugeordnete Dokumente werden nur gezählt, nicht ausgegeben "
        "(Mandantenschalter, AC07-01).",
    ),
    "include_portal_account": (
        "portal_account",
        "Portalkonto, Anmeldeereignisse und Sitzungen werden nur gezählt, nicht ausgegeben "
        "(Mandantenschalter, AC07-01).",
    ),
    "include_payments": (
        "payments",
        "Zahlungsdaten (Forderungen und Zahlungseingänge der Verträge) werden nur gezählt, "
        "nicht ausgegeben (Mandantenschalter, AC07-01).",
    ),
    "include_contracts": (
        "contracts",
        "Vertragsdaten (Miet- und Eigentumsverhältnisse) werden nur gezählt, nicht ausgegeben "
        "(Mandantenschalter, AC07-01).",
    ),
}
TICKET_FIELDS = ("number", "title", "public_description", "status", "created_at")
MESSAGE_FIELDS = ("channel", "direction", "subject", "body", "received_at", "sent_at")
DOCUMENT_FIELDS = ("title", "filename", "created_at")
PORTAL_ACCOUNT_FIELDS = (
    "status",
    "roles",
    "invited_at",
    "activated_at",
    "magic_link_2fa",
    "locale",
    "created_at",
)
CONTRACT_FIELDS = (
    "kind",
    "number",
    "start_date",
    "end_date",
    "termination_date",
    "direct_debit",
)
# Security events of the portal user that describe its own logins and sessions (AK06).
PORTAL_LOGIN_EVENTS = (
    "auth.login_succeeded",
    "auth.login_failed",
    "auth.account_locked",
    "auth.session_revoked",
)
OPEN_ITEM_FIELDS = ("kind", "component", "booking_date", "due_date", "written_off")


def withheld_for(options: ExportOptions) -> dict[str, str]:
    out = dict(WITHHELD)
    if options.include_internal_notes:
        del out["internal_notes"]
    for switch, (key, text_) in WITHHELD_SOURCES.items():
        if not getattr(options, switch):
            out[key] = text_
    if options.third_party_scope == SCOPE_NAMES:
        out["third_parties"] = (
            "Angaben zu anderen Personen werden mit Namen und Rolle ausgegeben, ohne "
            "Anschrift, Kontaktdaten, Kennungen und Bankdaten (Mandantenschalter, AC07-01)."
        )
    return out


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value") and not isinstance(value, str | int | float | bool):
        return value.value  # enums
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


def pick(source: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Allowlist projection of a schema, ORM row or dict."""
    out: dict[str, Any] = {}
    for name in fields:
        raw = source.get(name) if isinstance(source, dict) else getattr(source, name, None)
        out[name] = _jsonable(raw)
    return out


def _is_forbidden_key(key: str) -> bool:
    name = key.lower()
    return is_secret_key(name) or "hash" in name or "fingerprint" in name or name.endswith("_enc")


def strip_secrets(value: Any) -> Any:
    """Second line of defence behind the allowlist: drop every secret looking key."""
    if isinstance(value, dict):
        return {k: strip_secrets(v) for k, v in value.items() if not _is_forbidden_key(str(k))}
    if isinstance(value, list):
        return [strip_secrets(v) for v in value]
    return value


def content_hash(content: dict[str, Any]) -> str:
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _label(names: dict[uuid.UUID, str], contact_id: uuid.UUID) -> str:
    """Name of another person when the scope allows it (``names`` is empty otherwise)."""
    return names.get(contact_id) or THIRD_PARTY_PLACEHOLDER


async def _names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Contact.id, Contact.display_name).where(Contact.id.in_(ids))
    )
    return {cid: str(name or "") for cid, name in rows.all()}


async def build(
    session: AsyncSession,
    contact_id: uuid.UUID,
    generated_at: datetime,
    options: ExportOptions | None = None,
) -> dict[str, Any] | None:
    from mhvp.contacts import services  # local: services is large and imports widely

    options = options or ExportOptions()
    with_names = options.third_party_scope == SCOPE_NAMES

    contact = await services.load(session, contact_id)
    if contact is None:
        return None

    async def rows(model: Any) -> list[Any]:
        return list(
            (
                await session.scalars(
                    select(model).where(model.contact_id == contact_id).order_by(model.id)
                )
            ).all()
        )

    accounts = await rows(ContactBankAccount)
    notes = await rows(ContactNote)
    consents = await rows(Consent)
    relations = await rows(ContactRelation)
    parties = (
        await session.execute(
            select(Party.id, PartyMember.role)
            .join(PartyMember, PartyMember.party_id == Party.id)
            .where(PartyMember.contact_id == contact_id)
            .order_by(Party.id)
        )
    ).all()
    co_members: dict[uuid.UUID, list[tuple[uuid.UUID, Any]]] = {}
    for party_id, _ in parties:
        co_members[party_id] = [
            (cid, member_role)
            for cid, member_role in (
                await session.execute(
                    select(PartyMember.contact_id, PartyMember.role)
                    .where(PartyMember.party_id == party_id, PartyMember.contact_id != contact_id)
                    .order_by(PartyMember.id)
                )
            ).all()
        ]
    names: dict[uuid.UUID, str] = {}
    if with_names:
        names = await _names(
            session,
            {r.related_contact_id for r in relations}
            | {cid for members in co_members.values() for cid, _ in members},
        )
    events = (
        await session.scalars(
            select(DomainEvent)
            .where(
                DomainEvent.entity_id == contact_id,
                DomainEvent.entity_type == "contact",
                DomainEvent.occurred_at <= generated_at,
            )
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        )
    ).all()
    own_name = (contact.display_name or "").strip().casefold()
    bank_accounts = []
    for account in accounts:
        item = pick(account, BANK_FIELDS)
        holder = (account.holder or "").strip()
        # A different holder is another person (joint account, payer): role only.
        item["holder"] = (
            holder
            if not holder or holder.casefold() == own_name or with_names
            else THIRD_PARTY_PLACEHOLDER
        )
        bank_accounts.append(item)
    content: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "contact": {
            **pick(contact, CONTACT_FIELDS),
            "addresses": [pick(a, ADDRESS_FIELDS) for a in contact.addresses],
            "phones": [pick(p, PHONE_FIELDS) for p in contact.phones],
            "emails": [pick(e, EMAIL_FIELDS) for e in contact.emails],
            "identifiers": [pick(i, IDENTIFIER_FIELDS) for i in contact.identifiers],
            "dates": [pick(d, DATE_FIELDS) for d in contact.dates],
        },
        "bank_accounts": bank_accounts,
        "consents": [pick(c, CONSENT_FIELDS) for c in consents],
        "relations": [
            {
                "kind": _jsonable(r.kind),
                "related_person": _label(names, r.related_contact_id),
            }
            for r in relations
        ],
        "parties": [
            {
                "own_role": _jsonable(role),
                "further_members": len(co_members[party_id]),
                **(
                    {
                        "members": [
                            {
                                "name": _label(names, cid),
                                "role": _jsonable(member_role),
                            }
                            for cid, member_role in co_members[party_id]
                        ]
                    }
                    if with_names
                    else {}
                ),
            }
            for party_id, role in parties
        ],
        "processing_log": [
            {"type": e.type, "occurred_at": e.occurred_at.isoformat()} for e in events
        ],
        "withheld": {"categories": withheld_for(options)},
    }
    if options.include_internal_notes:
        content["internal_notes"] = {
            "contact_note": contact.notes,
            "notes": [pick(n, NOTE_FIELDS) for n in notes],
        }
    else:
        content["withheld"]["internal_notes_count"] = len(notes) + (1 if contact.notes else 0)
    await _add_sources(session, contact_id, options, content)
    await _add_account_and_contracts(session, contact_id, generated_at, options, content)
    result: dict[str, Any] = strip_secrets(content)
    return result


async def _add_sources(
    session: AsyncSession, contact_id: uuid.UUID, options: ExportOptions, content: dict[str, Any]
) -> None:
    """Tickets, messages and linked documents of the contact (GAI-506). Internal ticket
    descriptions, recipient lists of messages and document contents are never included."""
    from sqlalchemy import func, or_

    from mhvp.communication.models import Message
    from mhvp.documents.models import Document, DocumentLink
    from mhvp.tickets.models import Ticket

    ticket_where = or_(Ticket.contact_id == contact_id, Ticket.initiator_contact_id == contact_id)
    doc_where = (DocumentLink.entity_type == "contact") & (DocumentLink.entity_id == contact_id)
    counts = content["withheld"]
    if options.include_tickets:
        content["tickets"] = [
            pick(t, TICKET_FIELDS)
            for t in await session.scalars(
                select(Ticket).where(ticket_where).order_by(Ticket.created_at, Ticket.id)
            )
        ]
    else:
        counts["tickets_count"] = int(
            await session.scalar(select(func.count()).select_from(Ticket).where(ticket_where)) or 0
        )
    if options.include_communication:
        content["communication"] = [
            pick(m, MESSAGE_FIELDS)
            for m in await session.scalars(
                select(Message)
                .where(Message.contact_id == contact_id)
                .order_by(Message.created_at, Message.id)
            )
        ]
    else:
        counts["communication_count"] = int(
            await session.scalar(
                select(func.count()).select_from(Message).where(Message.contact_id == contact_id)
            )
            or 0
        )
    if options.include_documents:
        content["documents"] = [
            pick(d, DOCUMENT_FIELDS)
            for d in await session.scalars(
                select(Document)
                .join(DocumentLink, DocumentLink.document_id == Document.id)
                .where(doc_where)
                .distinct()
                .order_by(Document.created_at, Document.id)
            )
        ]
    else:
        counts["documents_count"] = int(
            await session.scalar(
                select(func.count(func.distinct(DocumentLink.document_id))).where(doc_where)
            )
            or 0
        )


async def _add_account_and_contracts(
    session: AsyncSession,
    contact_id: uuid.UUID,
    generated_at: datetime,
    options: ExportOptions,
    content: dict[str, Any],
) -> None:
    """Portal account with login events and sessions, contracts and payment data of the
    contact (AK06, GAI-506). Only values fixed at ``generated_at`` are used (login events up
    to that time, session start and end before it) so the release and every download
    reproduce the reviewed hash. Token hashes, codes and other secrets are never read."""
    from sqlalchemy import func

    from mhvp.accounting.models import OpenItem, OpenItemSettlement
    from mhvp.contracts.models import Contract
    from mhvp.platform.models import RefreshToken
    from mhvp.portal.models import PortalAccount

    counts = content["withheld"]
    account = await session.scalar(
        select(PortalAccount).where(PortalAccount.contact_id == contact_id)
    )
    if not options.include_portal_account:
        counts["portal_account_count"] = 1 if account is not None else 0
    elif account is None:
        content["portal_account"] = None
    else:
        events = (
            await session.scalars(
                select(DomainEvent)
                .where(
                    DomainEvent.entity_type == "user",
                    DomainEvent.entity_id == account.user_id,
                    DomainEvent.type.in_(PORTAL_LOGIN_EVENTS),
                    DomainEvent.occurred_at <= generated_at,
                )
                .order_by(DomainEvent.occurred_at, DomainEvent.id)
            )
        ).all()
        tokens = (
            await session.scalars(
                select(RefreshToken)
                .where(
                    RefreshToken.user_id == account.user_id,
                    RefreshToken.tenant_id == account.tenant_id,
                    RefreshToken.issued_at <= generated_at,
                )
                .order_by(RefreshToken.issued_at, RefreshToken.id)
            )
        ).all()
        families: dict[uuid.UUID, dict[str, Any]] = {}
        for t in tokens:
            fam = families.setdefault(
                t.family_id,
                {
                    "started_at": t.issued_at.isoformat(),
                    "user_agent": t.user_agent,
                    "ended_at": None,
                },
            )
            if t.revoked_at is not None and t.revoked_at <= generated_at:
                fam["ended_at"] = t.revoked_at.isoformat()
        content["portal_account"] = {
            **pick(account, PORTAL_ACCOUNT_FIELDS),
            "login_events": [
                {"type": e.type, "occurred_at": e.occurred_at.isoformat()} for e in events
            ],
            "sessions": list(families.values()),
        }
    party_ids = select(PartyMember.party_id).where(PartyMember.contact_id == contact_id)
    contract_where = Contract.party_id.in_(party_ids)
    if options.include_contracts:
        content["contracts"] = [
            pick(c, CONTRACT_FIELDS)
            for c in await session.scalars(
                select(Contract).where(contract_where).order_by(Contract.start_date, Contract.id)
            )
        ]
    else:
        counts["contracts_count"] = int(
            await session.scalar(select(func.count()).select_from(Contract).where(contract_where))
            or 0
        )
    item_where = OpenItem.contract_id.in_(select(Contract.id).where(contract_where))
    if options.include_payments:
        items = (
            await session.scalars(
                select(OpenItem)
                .where(item_where, OpenItem.created_at <= generated_at)
                .order_by(OpenItem.booking_date, OpenItem.id)
            )
        ).all()
        numbers: dict[uuid.UUID, str] = {
            cid: str(num)
            for cid, num in (
                await session.execute(select(Contract.id, Contract.number).where(contract_where))
            ).all()
        }
        payments = []
        for item in items:
            settled = await session.scalar(
                select(func.coalesce(func.sum(OpenItemSettlement.amount), 0)).where(
                    OpenItemSettlement.open_item_id == item.id,
                    OpenItemSettlement.created_at <= generated_at,
                )
            )
            payments.append(
                {
                    **pick(item, OPEN_ITEM_FIELDS),
                    "contract_number": (
                        numbers.get(item.contract_id) if item.contract_id else None
                    ),
                    "amount": f"{item.amount:.2f}",
                    "settled": f"{settled:.2f}",
                }
            )
        content["payments"] = payments
    else:
        counts["payments_count"] = int(
            await session.scalar(select(func.count()).select_from(OpenItem).where(item_where)) or 0
        )


@dataclass
class AccessExport:
    id: uuid.UUID
    contact_id: uuid.UUID
    status: str
    sha256: str
    generated_at: datetime
    prepared_by: uuid.UUID | None
    prepared_at: datetime
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    released_by: uuid.UUID | None = None
    released_at: datetime | None = None
    rejected_reason: str | None = None
    downloads: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)
    options: ExportOptions = field(default_factory=ExportOptions)

    @property
    def third_party_scope(self) -> str:
        return self.options.third_party_scope

    @property
    def internal_notes_included(self) -> bool:
        return self.options.include_internal_notes


def _fold(events: list[DomainEvent]) -> AccessExport | None:
    if not events or events[0].type != EVENT_PREPARED:
        return None
    first = events[0]
    export = AccessExport(
        id=uuid.UUID(str(first.entity_id)),
        contact_id=uuid.UUID(first.payload["contact_id"]),
        status=STATUS_PREPARED,
        sha256=first.payload["sha256"],
        generated_at=datetime.fromisoformat(first.payload["generated_at"]),
        prepared_by=first.actor_user_id,
        prepared_at=first.occurred_at,
        options=ExportOptions.from_dict(first.payload.get("options")),
    )
    for event in events:
        export.log.append(
            {
                "type": event.type,
                "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                "occurred_at": event.occurred_at.isoformat(),
            }
        )
        if event.type == EVENT_REVIEWED:
            export.reviewed_by, export.reviewed_at = event.actor_user_id, event.occurred_at
        elif event.type == EVENT_RELEASED:
            export.released_by, export.released_at = event.actor_user_id, event.occurred_at
        elif event.type == EVENT_REJECTED:
            export.rejected_reason = event.payload.get("reason")
        elif event.type == EVENT_DOWNLOADED:
            export.downloads += 1
        export.status = _STATUS_BY_EVENT.get(event.type, export.status)
    return export


async def get(session: AsyncSession, export_id: uuid.UUID) -> AccessExport | None:
    events = list(
        (
            await session.scalars(
                select(DomainEvent)
                .where(DomainEvent.entity_type == ENTITY_TYPE, DomainEvent.entity_id == export_id)
                .order_by(DomainEvent.occurred_at, DomainEvent.id)
            )
        ).all()
    )
    return _fold(events)


async def list_for_contact(session: AsyncSession, contact_id: uuid.UUID) -> list[AccessExport]:
    ids = (
        await session.scalars(
            select(DomainEvent.entity_id)
            .where(
                DomainEvent.entity_type == ENTITY_TYPE,
                DomainEvent.type == EVENT_PREPARED,
                DomainEvent.payload["contact_id"].astext == str(contact_id),
            )
            .order_by(DomainEvent.occurred_at.desc())
        )
    ).all()
    out = []
    for export_id in ids:
        if export_id is not None and (item := await get(session, export_id)) is not None:
            out.append(item)
    return out


async def _emit(
    session: AsyncSession,
    export: AccessExport,
    tenant_id: uuid.UUID,
    type_: str,
    actor: uuid.UUID | None,
    **payload: Any,
) -> None:
    await emit(
        session,
        tenant_id=tenant_id,
        type=type_,
        entity_type=ENTITY_TYPE,
        entity_id=export.id,
        actor_user_id=actor,
        payload={"contact_id": str(export.contact_id), "sha256": export.sha256, **payload},
    )


async def prepare(
    session: AsyncSession, *, tenant_id: uuid.UUID, contact_id: uuid.UUID, actor: uuid.UUID | None
) -> AccessExport | None:
    _person(actor)
    generated_at = datetime.now(UTC).replace(microsecond=0)
    options = await current_options(session)
    content = await build(session, contact_id, generated_at, options)
    if content is None:
        return None
    export_id = uuid.uuid4()
    digest = content_hash(content)
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_PREPARED,
        entity_type=ENTITY_TYPE,
        entity_id=export_id,
        actor_user_id=actor,
        payload={
            "contact_id": str(contact_id),
            "sha256": digest,
            "generated_at": generated_at.isoformat(),
            "options": options.as_dict(),
        },
    )
    return await get(session, export_id)


def _require(export: AccessExport, *states: str) -> None:
    if export.status not in states:
        raise ProblemError(ErrorCodes.CONTACT_ACCESS_EXPORT_STATE)


def _person(actor: uuid.UUID | None) -> uuid.UUID:
    if actor is None:  # API keys cannot take part in a four eyes workflow
        raise ProblemError(ErrorCodes.CONTACT_ACCESS_EXPORT_FOUR_EYES)
    return actor


def _second_person(export: AccessExport, actor: uuid.UUID | None) -> None:
    if _person(actor) == export.prepared_by:
        raise ProblemError(ErrorCodes.CONTACT_ACCESS_EXPORT_FOUR_EYES)


async def _rebuild_checked(session: AsyncSession, export: AccessExport) -> dict[str, Any]:
    content = await build(session, export.contact_id, export.generated_at, export.options)
    if content is None or content_hash(content) != export.sha256:
        raise ProblemError(ErrorCodes.CONTACT_ACCESS_EXPORT_CHANGED)
    return content


async def review(
    session: AsyncSession, export: AccessExport, *, tenant_id: uuid.UUID, actor: uuid.UUID | None
) -> AccessExport:
    _require(export, STATUS_PREPARED)
    _second_person(export, actor)
    await _rebuild_checked(session, export)
    await _emit(session, export, tenant_id, EVENT_REVIEWED, actor)
    return await get(session, export.id) or export


async def release(
    session: AsyncSession, export: AccessExport, *, tenant_id: uuid.UUID, actor: uuid.UUID | None
) -> AccessExport:
    _require(export, STATUS_REVIEWED)
    _second_person(export, actor)
    await _rebuild_checked(session, export)
    await _emit(session, export, tenant_id, EVENT_RELEASED, actor)
    return await get(session, export.id) or export


async def reject(
    session: AsyncSession,
    export: AccessExport,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    reason: str,
) -> AccessExport:
    _require(export, STATUS_PREPARED, STATUS_REVIEWED)
    await _emit(session, export, tenant_id, EVENT_REJECTED, actor, reason=reason)
    return await get(session, export.id) or export


async def preview(session: AsyncSession, export: AccessExport) -> dict[str, Any]:
    """Content for the reviewer (internal, not a release)."""
    _require(export, STATUS_PREPARED, STATUS_REVIEWED, STATUS_RELEASED)
    return await _rebuild_checked(session, export)


async def download(
    session: AsyncSession, export: AccessExport, *, tenant_id: uuid.UUID, actor: uuid.UUID | None
) -> dict[str, Any]:
    _require(export, STATUS_RELEASED)
    content = await _rebuild_checked(session, export)
    await _emit(session, export, tenant_id, EVENT_DOWNLOADED, actor)
    return {
        "export_id": str(export.id),
        "status": STATUS_RELEASED,
        "reviewed_by": str(export.reviewed_by),
        "released_by": str(export.released_by),
        "released_at": export.released_at.isoformat() if export.released_at else None,
        "sha256": export.sha256,
        **content,
    }
