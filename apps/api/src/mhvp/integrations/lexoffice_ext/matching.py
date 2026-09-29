"""Deterministic contact matching by name and e mail with review (operator decision
28.09.2026: no shared customer number). Scores: ``customer_number`` 1.0 (only when the CRM
contact carries a Lexware number in ``external_ids``), ``email_exact`` 0.9, ``name_zip`` 0.7,
``name_only`` 0.4. A remote contact is proposed to at most one CRM contact; equal top scores
make the row ``ambiguous``. Nothing is written to Lexware by a match run.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactAddress, ContactEmail
from mhvp.integrations.lexoffice_async import LexofficeAsyncClient, LexofficeError
from mhvp.integrations.lexoffice_ext import payloads, services
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeLinkStatus,
    LexofficeOutboxKind,
    LexofficeRunKind,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)

PROPOSAL_THRESHOLD = 0.7
LEGAL_FORMS = (
    "gmbh und co. kg",
    "gmbh und co kg",
    "und co. kg",
    "und co kg",
    "gmbh",
    "ag",
    "kg",
    "gbr",
    "ug",
    "e.k.",
    "ek",
    "ohg",
    "mbh",
    "e.v.",
    "ev",
)
UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
UNTOUCHED = frozenset(
    {
        LexofficeLinkStatus.LINKED.value,
        LexofficeLinkStatus.SYNCED.value,
        LexofficeLinkStatus.PENDING.value,
        LexofficeLinkStatus.CONFLICT.value,
        LexofficeLinkStatus.MANUAL_REQUIRED.value,
        LexofficeLinkStatus.ERROR.value,
        LexofficeLinkStatus.DISMISSED.value,
        LexofficeLinkStatus.REMOTE_MISSING.value,
    }
)


def normalise_name(value: str | None) -> str:
    text = (value or "").lower()
    for src, dst in UMLAUTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = " ".join(text.replace("&", " und ").split())
    for form in LEGAL_FORMS:
        text = re.sub(rf"(^|\s){re.escape(form)}(?=\s|$)", " ", text)
    text = re.sub(r"\bund\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    # Token order is irrelevant ("Harter, Hardy" equals "Hardy Harter").
    return " ".join(sorted(text.split()))


def normalise_street(value: str | None) -> str:
    text = normalise_name(value)
    text = re.sub(r"str(?:asse|\.)?\b", "strasse", text)
    return text


@dataclass
class CrmContact:
    id: uuid.UUID
    name: str
    zip: str | None
    emails: set[str]
    customer_number: int | None = None


@dataclass
class RemoteContact:
    id: str
    display: dict[str, Any]
    name: str
    zip: str | None
    emails: set[str]
    customer_number: int | None
    vendor_number: int | None
    archived: bool
    multi_entry: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    contact_id: uuid.UUID
    reason: str
    score: float


def remote_from_json(remote: dict[str, Any]) -> RemoteContact:
    managed = payloads.remote_managed_values(remote)
    roles = remote.get("roles") or {}
    emails: set[str] = set()
    for values in (remote.get("emailAddresses") or {}).values():
        if isinstance(values, list):
            emails |= {str(v).strip().lower() for v in values if v}
    for person in (remote.get("company") or {}).get("contactPersons") or []:
        if isinstance(person, dict) and person.get("emailAddress"):
            emails.add(str(person["emailAddress"]).strip().lower())
    addr = managed.get("billing_address") or {}
    return RemoteContact(
        id=str(remote.get("id")),
        display={
            "name": payloads.display_name(managed),
            "kind": managed["kind"],
            "customer_number": (roles.get("customer") or {}).get("number"),
            "vendor_number": (roles.get("vendor") or {}).get("number"),
            "email": next(iter(sorted(emails)), None),
            "city": addr.get("city"),
            "zip": addr.get("zip"),
            "archived": bool(remote.get("archived")),
            "updated_date": remote.get("updatedDate"),
            "multi_entry_lists": payloads.multi_entry_lists(remote),
        },
        name=normalise_name(payloads.display_name(managed)),
        zip=(addr.get("zip") or None),
        emails=emails,
        customer_number=(roles.get("customer") or {}).get("number"),
        vendor_number=(roles.get("vendor") or {}).get("number"),
        archived=bool(remote.get("archived")),
        multi_entry=payloads.multi_entry_lists(remote),
    )


def score(remote: RemoteContact, crm: CrmContact) -> Candidate | None:
    numbers = {n for n in (remote.customer_number, remote.vendor_number) if n is not None}
    if crm.customer_number is not None and crm.customer_number in numbers:
        return Candidate(crm.id, "customer_number", 1.0)
    if remote.emails and crm.emails & remote.emails:
        return Candidate(crm.id, "email_exact", 0.9)
    if remote.name and crm.name and remote.name == crm.name:
        if remote.zip and crm.zip and remote.zip == crm.zip:
            return Candidate(crm.id, "name_zip", 0.7)
        return Candidate(crm.id, "name_only", 0.4)
    return None


def assign(
    remotes: list[RemoteContact], contacts: list[CrmContact]
) -> dict[str, tuple[str, list[Candidate]]]:
    """Returns ``remote id -> (status, candidates)`` with ``proposed``, ``ambiguous`` or
    ``remote_only``. Greedy by descending score, then stable by remote id."""
    scored: dict[str, list[Candidate]] = {}
    for remote in remotes:
        found = [c for c in (score(remote, crm) for crm in contacts) if c is not None]
        found.sort(key=lambda c: (-c.score, str(c.contact_id)))
        scored[remote.id] = found
    taken: set[uuid.UUID] = set()
    result: dict[str, tuple[str, list[Candidate]]] = {}
    order = sorted(remotes, key=lambda r: (-(scored[r.id][0].score if scored[r.id] else 0.0), r.id))
    for remote in order:
        candidates = [c for c in scored[remote.id] if c.contact_id not in taken]
        if not candidates or candidates[0].score < PROPOSAL_THRESHOLD:
            result[remote.id] = ("remote_only", candidates[:3])
            continue
        top = candidates[0].score
        tied = [c for c in candidates if c.score == top]
        if len(tied) > 1:
            result[remote.id] = ("ambiguous", tied)
            continue
        taken.add(candidates[0].contact_id)
        result[remote.id] = ("proposed", candidates[:1])
    return result


async def load_crm_contacts(session: AsyncSession, tenant_id: uuid.UUID) -> list[CrmContact]:
    contacts = (
        await session.scalars(
            select(Contact).where(Contact.tenant_id == tenant_id, Contact.deleted_at.is_(None))
        )
    ).all()
    emails_by_contact: dict[uuid.UUID, set[str]] = {}
    for email in await session.scalars(
        select(ContactEmail).where(ContactEmail.tenant_id == tenant_id)
    ):
        emails_by_contact.setdefault(email.contact_id, set()).add(email.email.strip().lower())
    zip_by_contact: dict[uuid.UUID, str] = {}
    for addr in await session.scalars(
        select(ContactAddress).where(ContactAddress.tenant_id == tenant_id)
    ):
        if addr.postal_code and (
            addr.contact_id not in zip_by_contact or str(addr.label) == "postal" or addr.is_primary
        ):
            zip_by_contact[addr.contact_id] = addr.postal_code
    out: list[CrmContact] = []
    for contact in contacts:
        number_raw = (contact.external_ids or {}).get("lexoffice_customer_number")
        number = int(str(number_raw)) if str(number_raw or "").isdigit() else None
        out.append(
            CrmContact(
                id=contact.id,
                name=normalise_name(contact.display_name),
                zip=zip_by_contact.get(contact.id),
                emails=emails_by_contact.get(contact.id, set()),
                customer_number=number,
            )
        )
    return out


async def run_match(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    config: LexofficeTenantConfig,
    client: LexofficeAsyncClient,
    run: LexofficeSyncRun,
    *,
    scope: str = "customers_and_vendors",
) -> dict[str, int]:
    counts = {
        "pages": 0,
        "remote": 0,
        "proposed": 0,
        "ambiguous": 0,
        "remote_only": 0,
        "refreshed": 0,
    }
    errors: list[str] = []
    remotes: dict[str, RemoteContact] = {}
    filters: list[tuple[bool | None, bool | None]] = (
        [(True, None), (None, True)] if scope == "customers_and_vendors" else [(None, None)]
    )
    try:
        for customer, vendor in filters:
            page = 0
            while True:
                body = await client.list_contacts(
                    page=page, size=250, customer=customer, vendor=vendor
                )
                counts["pages"] += 1
                for item in body.get("content") or []:
                    if isinstance(item, dict) and item.get("id"):
                        remotes[str(item["id"])] = remote_from_json(item)
                if body.get("last", True) or page + 1 >= int(body.get("totalPages") or 1):
                    break
                page += 1
    except LexofficeError as exc:
        errors.append(exc.redacted())
    counts["remote"] = len(remotes)
    existing = {
        link.lexoffice_contact_id: link
        for link in await session.scalars(
            select(LexofficeContactLink).where(LexofficeContactLink.config_id == config.id)
        )
        if link.lexoffice_contact_id
    }
    contacts = await load_crm_contacts(session, tenant_id)
    linked_contact_ids = {
        link.contact_id
        for link in existing.values()
        if link.contact_id is not None and link.sync_status in UNTOUCHED
    }
    fresh = [
        r
        for rid, r in remotes.items()
        if rid not in existing or existing[rid].sync_status not in UNTOUCHED
    ]
    assignment = assign(fresh, [c for c in contacts if c.id not in linked_contact_ids])
    now = datetime.now(UTC)
    for remote_id, remote in remotes.items():
        link = existing.get(remote_id)
        if link is not None and link.sync_status in UNTOUCHED:
            link.remote_display = remote.display
            link.customer_number = remote.customer_number
            link.vendor_number = remote.vendor_number
            if remote.archived:
                link.sync_status = LexofficeLinkStatus.REMOTE_MISSING.value
            elif remote.multi_entry:
                link.sync_status = LexofficeLinkStatus.MANUAL_REQUIRED.value
                link.last_error = (
                    "Mehrfach belegte Listen in Lexware Office, bitte dort bereinigen."
                )
            elif link.sync_status in (
                LexofficeLinkStatus.REMOTE_MISSING.value,
                LexofficeLinkStatus.MANUAL_REQUIRED.value,
            ):
                link.sync_status = LexofficeLinkStatus.LINKED.value
                link.last_error = None
            counts["refreshed"] += 1
            continue
        status, candidates = assignment[remote_id]
        if link is None:
            link = LexofficeContactLink(
                tenant_id=tenant_id, config_id=config.id, sync_status=status, updated_at=now
            )
            session.add(link)
        link.sync_status = status
        link.remote_display = remote.display
        link.customer_number = remote.customer_number
        link.vendor_number = remote.vendor_number
        link.proposed_lexoffice_contact_id = remote_id
        link.lexoffice_contact_id = remote_id
        link.candidates = [
            {"contact_id": str(c.contact_id), "reason": c.reason, "score": c.score}
            for c in candidates
        ]
        if status == "proposed":
            link.contact_id = candidates[0].contact_id
            link.match_reason = candidates[0].reason
            link.match_score = candidates[0].score  # type: ignore[assignment]
        else:
            link.contact_id = None
            link.match_reason = None
            link.match_score = None
        counts[status] += 1
    await session.flush()
    await services.finish_run(session, run, counts, errors)
    return counts


# Decisions ----------------------------------------------------------------------------------

DECIDABLE = frozenset(
    {
        LexofficeLinkStatus.PROPOSED.value,
        LexofficeLinkStatus.AMBIGUOUS.value,
        LexofficeLinkStatus.REMOTE_ONLY.value,
        LexofficeLinkStatus.REMOTE_MISSING.value,
        LexofficeLinkStatus.DISMISSED.value,
        LexofficeLinkStatus.UNLINKED_LOCAL.value,
    }
)


async def _refresh_row(
    session: AsyncSession, link: LexofficeContactLink, actor: uuid.UUID | None
) -> None:
    await services.enqueue(
        session,
        tenant_id=link.tenant_id,
        config_id=link.config_id,
        kind=LexofficeOutboxKind.REFRESH_LINK,
        idempotency_key=f"link-refresh-{link.id}-{uuid.uuid4().hex[:8]}",
        target_kind="link",
        target_id=link.id,
        requested_by=actor,
    )


async def link_existing(
    session: AsyncSession,
    link: LexofficeContactLink,
    *,
    lexoffice_contact_id: str | None,
    contact_id: uuid.UUID | None,
    actor: uuid.UUID | None,
) -> None:
    from mhvp.core.problems import ErrorCodes, ProblemError

    if link.sync_status not in DECIDABLE:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Diese Zeile ist bereits entschieden.")
    remote_id = (
        lexoffice_contact_id or link.lexoffice_contact_id or link.proposed_lexoffice_contact_id
    )
    target = contact_id or link.contact_id
    if not remote_id or target is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Lexware Kontakt und CRM Kontakt sind nötig."
        )
    other = await session.scalar(
        select(LexofficeContactLink).where(
            LexofficeContactLink.config_id == link.config_id,
            LexofficeContactLink.contact_id == target,
            LexofficeContactLink.id != link.id,
        )
    )
    if other is not None:
        if other.sync_status in UNTOUCHED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der CRM Kontakt ist bereits verknüpft.")
        await session.delete(other)
    link.contact_id = target
    link.lexoffice_contact_id = remote_id
    link.sync_status = LexofficeLinkStatus.PENDING.value
    link.match_reason = link.match_reason if link.contact_id == target else "manual"
    link.decided_by = actor
    link.decided_at = datetime.now(UTC)
    await session.flush()
    await _refresh_row(session, link, actor)


async def create_remote(
    session: AsyncSession,
    config: LexofficeTenantConfig,
    contact_id: uuid.UUID,
    roles: list[str],
    actor: uuid.UUID | None,
) -> LexofficeContactLink:
    from mhvp.core.problems import ErrorCodes, ProblemError

    if not roles:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Mindestens eine Rolle wählen.")
    link = await session.scalar(
        select(LexofficeContactLink).where(
            LexofficeContactLink.config_id == config.id,
            LexofficeContactLink.contact_id == contact_id,
        )
    )
    if link is not None and link.sync_status in UNTOUCHED and link.lexoffice_contact_id:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Kontakt ist bereits verknüpft.")
    if link is None:
        link = LexofficeContactLink(
            tenant_id=config.tenant_id,
            config_id=config.id,
            contact_id=contact_id,
            sync_status=LexofficeLinkStatus.PENDING.value,
        )
        session.add(link)
    link.sync_status = LexofficeLinkStatus.PENDING.value
    link.lexoffice_contact_id = None
    link.proposed_lexoffice_contact_id = None
    link.match_reason = "manual"
    link.decided_by = actor
    link.decided_at = datetime.now(UTC)
    await session.flush()
    await services.enqueue(
        session,
        tenant_id=config.tenant_id,
        config_id=config.id,
        kind=LexofficeOutboxKind.CONTACT_CREATE,
        idempotency_key=f"contact-create-{contact_id}-cfg{config.id}",
        target_kind="contact",
        target_id=contact_id,
        payload={"roles": sorted(set(roles))},
        requested_by=actor,
    )
    return link


async def push(
    session: AsyncSession,
    link: LexofficeContactLink,
    *,
    fields: set[str],
    force: bool,
    actor: uuid.UUID | None,
) -> None:
    from mhvp.core.problems import ErrorCodes, ProblemError

    if link.contact_id is None or not link.lexoffice_contact_id:
        raise ProblemError(ErrorCodes.LEXOFFICE_CONTACT_NOT_LINKED)
    contact = await session.get(Contact, link.contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.LEXOFFICE_CONTACT_NOT_LINKED)
    await services.enqueue(
        session,
        tenant_id=link.tenant_id,
        config_id=link.config_id,
        kind=LexofficeOutboxKind.CONTACT_UPDATE,
        idempotency_key=f"contact-push-{link.contact_id}-cfg{link.config_id}-v{contact.version}-{uuid.uuid4().hex[:6]}",
        target_kind="contact",
        target_id=link.contact_id,
        payload={
            "contact_id": str(link.contact_id),
            "contact_version": contact.version,
            "fields": sorted(fields),
            "source": "manual",
            "force": force,
        },
        requested_by=actor,
    )
    link.sync_status = LexofficeLinkStatus.PENDING.value


async def start_match_run(
    session: AsyncSession, config: LexofficeTenantConfig, actor: uuid.UUID | None
) -> LexofficeSyncRun:
    from mhvp.core.problems import ErrorCodes, ProblemError

    running = await session.scalar(
        select(LexofficeSyncRun).where(
            LexofficeSyncRun.tenant_id == config.tenant_id,
            LexofficeSyncRun.kind == LexofficeRunKind.CONTACT_MATCH.value,
            LexofficeSyncRun.status == "running",
        )
    )
    if running is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Ein Abgleich läuft bereits.")
    return await services.start_run(
        session, config.tenant_id, LexofficeRunKind.CONTACT_MATCH, actor
    )
