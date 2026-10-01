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

    def as_dict(self) -> dict[str, Any]:
        return {
            "third_party_scope": self.third_party_scope,
            "include_internal_notes": self.include_internal_notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExportOptions:
        if not raw:
            return cls()
        scope = str(raw.get("third_party_scope", SCOPE_NONE))
        return cls(
            third_party_scope=scope if scope in THIRD_PARTY_SCOPES else SCOPE_NONE,
            include_internal_notes=bool(raw.get("include_internal_notes", False)),
        )


async def current_options(session: AsyncSession) -> ExportOptions:
    """Switches of the tenant; no row means the conservative defaults."""
    row = await session.scalar(select(ContactAccessExportSetting))
    if row is None:
        return ExportOptions()
    return ExportOptions.from_dict(
        {
            "third_party_scope": row.third_party_scope,
            "include_internal_notes": row.include_internal_notes,
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


def withheld_for(options: ExportOptions) -> dict[str, str]:
    out = dict(WITHHELD)
    if options.include_internal_notes:
        del out["internal_notes"]
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
    result: dict[str, Any] = strip_secrets(content)
    return result


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
