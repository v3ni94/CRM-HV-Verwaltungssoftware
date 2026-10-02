"""Art. 17 request for a contact: lock check, four eyes release, anonymisation (S711-08).

Rules (Entscheidung 10 a, 7.11 S06, rule 0.1.3): nothing is decided by assumption. The lock
check is deliberately conservative, every hit blocks:

* the deletion profile for data type ``contact`` must exist and be released,
* the contact needs a retention profile and its ``delete_after`` must have passed,
* no business record may reference the contact (every foreign key to ``contact.id`` outside
  the contact child tables, for example contracts, invoices, tickets, property roles),
* documents linked to the contact must have an expired retention period and no hold.

Execution anonymises (names, addresses, phones, e-mails, identifiers, dates, bank accounts,
notes), keeps the row and the consent records as evidence and never touches booked content.
Whether a blocked request may be answered with a restriction instead is a legal question for
a lawyer (V13); the response period of the request is to be verified.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.examples import delete_examples_for_contact
from mhvp.contacts.models import (
    Contact,
    ContactAddress,
    ContactBankAccount,
    ContactBankAccountChange,
    ContactDate,
    ContactEmail,
    ContactIdentifier,
    ContactNote,
    ContactPhone,
)
from mhvp.core.clock import local_today
from mhvp.core.db.base import Base
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentLink
from mhvp.privacy.models import PrivacyDeletionProfile, PrivacyErasureRequest

ANONYMIZED_PREFIX = "Anonymisiert"
_IGNORED_REFERENCING = {"privacy_erasure_request"}


def _referencing_columns() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if table.name.startswith("contact_") or table.name in _IGNORED_REFERENCING:
            continue
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == "contact" and fk.column.name == "id":
                    found.append((table.name, column.name))
    return found


async def blockers(
    session: AsyncSession, contact: Contact, today: date | None = None
) -> list[dict[str, Any]]:
    today = today or local_today()
    out: list[dict[str, Any]] = []
    if contact.display_name.startswith(ANONYMIZED_PREFIX):
        out.append(
            {"code": "already_anonymized", "detail": "Der Kontakt ist bereits anonymisiert."}
        )
    profile = await session.scalar(
        select(PrivacyDeletionProfile).where(PrivacyDeletionProfile.data_type == "contact")
    )
    if profile is None or not profile.released:
        out.append(
            {
                "code": "deletion_profile_not_released",
                "detail": "Das Löschprofil für Kontakte fehlt oder ist nicht freigegeben.",
            }
        )
    if contact.retention_profile_id is None:
        out.append(
            {
                "code": "no_retention_profile",
                "detail": (
                    "Dem Kontakt ist kein Aufbewahrungsprofil zugeordnet, "
                    "die Frist ist nicht geprüft."
                ),
            }
        )
    elif contact.delete_after is None or contact.delete_after > today:
        out.append(
            {
                "code": "retention_running",
                "detail": "Die Aufbewahrungsfrist läuft"
                + (f" bis {contact.delete_after:%d.%m.%Y}." if contact.delete_after else "."),
            }
        )
    present = {
        r[0]
        for r in (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                )
            )
        ).all()
    }
    for table, column in _referencing_columns():
        if table not in present:
            continue  # model ahead of its migration: no rows can exist
        count = await session.scalar(
            text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = :cid'),  # noqa: S608
            {"cid": contact.id},
        )
        if count:
            out.append(
                {
                    "code": "referenced",
                    "detail": f"Verknüpfung in {table}.{column} ({count} Einträge).",
                    "table": table,
                }
            )
    docs = (
        await session.execute(
            select(Document.id, Document.retention_until, Document.retention_hold_reason)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(DocumentLink.entity_type == "contact", DocumentLink.entity_id == contact.id)
        )
    ).all()
    locked = [
        d.id
        for d in docs
        if d.retention_hold_reason or d.retention_until is None or d.retention_until > today
    ]
    if locked:
        out.append(
            {
                "code": "documents_locked",
                "detail": f"{len(locked)} verknüpfte Dokumente mit Sperre oder laufender Frist.",
            }
        )
    return out


async def create_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    received_on: date,
    reason: str | None,
    user_id: uuid.UUID | None,
) -> PrivacyErasureRequest:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    request = PrivacyErasureRequest(
        tenant_id=tenant_id,
        contact_id=contact_id,
        received_on=received_on,
        reason=reason,
        requested_by=user_id,
        created_by=user_id,
        blockers=await blockers(session, contact),
    )
    session.add(request)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="privacy.erasure_requested",
        entity_type="contact",
        entity_id=contact_id,
        actor_user_id=user_id,
        payload={"request_id": str(request.id), "blocked": bool(request.blockers)},
    )
    return request


def _require(request: PrivacyErasureRequest, *statuses: str) -> None:
    if request.status not in statuses:
        raise ProblemError(ErrorCodes.PRIVACY_STATE)


async def approve(
    session: AsyncSession,
    request: PrivacyErasureRequest,
    user_id: uuid.UUID | None,
    note: str | None,
) -> PrivacyErasureRequest:
    _require(request, "requested")
    if user_id is None or user_id == request.requested_by:
        raise ProblemError(ErrorCodes.PRIVACY_FOUR_EYES)
    contact = await session.get(Contact, request.contact_id)
    if contact is None:  # FK RESTRICT, cannot happen
        raise ProblemError(ErrorCodes.NOT_FOUND)
    request.blockers = await blockers(session, contact)
    if request.blockers:
        raise ProblemError(
            ErrorCodes.PRIVACY_ERASURE_BLOCKED, extensions={"blockers": request.blockers}
        )
    request.status, request.decided_by, request.decided_at = "approved", user_id, datetime.now(UTC)
    request.decision_note = note
    await emit(
        session,
        tenant_id=request.tenant_id,
        type="privacy.erasure_approved",
        entity_type="contact",
        entity_id=request.contact_id,
        actor_user_id=user_id,
        payload={"request_id": str(request.id)},
    )
    return request


async def reject(
    session: AsyncSession,
    request: PrivacyErasureRequest,
    user_id: uuid.UUID | None,
    note: str | None,
) -> PrivacyErasureRequest:
    # A job proposal (AJ12, status ``proposed``) has no requester and may be dismissed by
    # any person with the approve permission; dismissing deletes nothing.
    _require(request, "proposed", "requested", "approved")
    if user_id is None or user_id == request.requested_by:
        raise ProblemError(ErrorCodes.PRIVACY_FOUR_EYES)
    request.status, request.decided_by, request.decided_at = "rejected", user_id, datetime.now(UTC)
    request.decision_note = note
    await emit(
        session,
        tenant_id=request.tenant_id,
        type="privacy.erasure_rejected",
        entity_type="contact",
        entity_id=request.contact_id,
        actor_user_id=user_id,
        payload={"request_id": str(request.id)},
    )
    return request


async def anonymize_contact(
    session: AsyncSession, contact: Contact, user_id: uuid.UUID | None
) -> dict[str, int]:
    """Removes the personal child rows and anonymises the contact row (no lock check, no event).

    Shared by :func:`execute` and the erasure journal replay after a restore (GAI-512)."""
    removed: dict[str, int] = {}
    accounts = select(ContactBankAccount.id).where(ContactBankAccount.contact_id == contact.id)
    res = await session.execute(
        delete(ContactBankAccountChange).where(
            ContactBankAccountChange.bank_account_id.in_(accounts)
        )
    )
    removed["contact_bank_account_change"] = int(res.rowcount or 0)  # type: ignore[attr-defined]
    for model in (
        ContactBankAccount,
        ContactAddress,
        ContactPhone,
        ContactEmail,
        ContactIdentifier,
        ContactDate,
        ContactNote,
    ):
        res = await session.execute(delete(model).where(model.contact_id == contact.id))
        removed[model.__tablename__] = int(res.rowcount or 0)  # type: ignore[attr-defined]
    await delete_examples_for_contact(session, contact.id)
    label = f"{ANONYMIZED_PREFIX} {str(contact.id)[:8]}"
    await session.execute(
        update(Contact)
        .where(Contact.id == contact.id)
        .values(
            salutation=None,
            letter_salutation=None,
            title=None,
            first_name=None,
            last_name=label if contact.kind.value == "person" else None,
            company_name=label if contact.kind.value == "company" else None,
            legal_form=None,
            position=None,
            date_of_birth=None,
            notes=None,
            blocked=True,
            external_ids={},
            display_name=label,
            search_text=label.lower(),
            source_system=None,
            source_id=None,
            deleted_at=func.now(),
            version=Contact.version + 1,
            updated_by=user_id,
        )
    )
    return removed


async def execute(
    session: AsyncSession, request: PrivacyErasureRequest, user_id: uuid.UUID | None
) -> PrivacyErasureRequest:
    """Anonymises the contact after a fresh lock check (state may have changed since release)."""
    _require(request, "approved")
    contact = await session.get(Contact, request.contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    found = await blockers(session, contact)
    if found:
        request.blockers = found
        raise ProblemError(ErrorCodes.PRIVACY_ERASURE_BLOCKED, extensions={"blockers": found})
    removed = await anonymize_contact(session, contact, user_id)
    request.status, request.executed_by, request.executed_at = (
        "executed",
        user_id,
        datetime.now(UTC),
    )
    request.result = {"removed": removed, "kept": ["consent", "domain_events"]}
    request.blockers = []
    await emit(
        session,
        tenant_id=request.tenant_id,
        type="contact.anonymized",
        entity_type="contact",
        entity_id=request.contact_id,
        actor_user_id=user_id,
        payload={"request_id": str(request.id)},
    )
    return request


async def accept_proposal(
    session: AsyncSession, request: PrivacyErasureRequest, user_id: uuid.UUID | None
) -> PrivacyErasureRequest:
    """A job proposal (AJ12, GAI-501) becomes a request of the accepting person (first person);
    the release stays with a second person (``approve``)."""
    _require(request, "proposed")
    contact = await session.get(Contact, request.contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    request.status, request.requested_by = "requested", user_id
    request.blockers = await blockers(session, contact)
    await emit(
        session,
        tenant_id=request.tenant_id,
        type="privacy.erasure_proposal_accepted",
        entity_type="contact",
        entity_id=request.contact_id,
        actor_user_id=user_id,
        payload={"request_id": str(request.id), "blocked": bool(request.blockers)},
    )
    return request
