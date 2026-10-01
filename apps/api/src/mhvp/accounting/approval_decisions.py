"""Central approval decisions and the person check of two approvers (6.9.9, E09).

* S69-02: every payment and invoice approval also writes an ``approval_decision`` with the
  hash of the approved subject (``subject_snapshot_hash``). The existing records
  (``payment_approval``, ``invoice.released_hash``, ``invoice_second_approval``) stay and keep
  deciding the checks; this table adds a persisted ``invalidated`` status when the subject
  changes, so the fall back to the state before approval is visible, not only computed.
* S69-03: :func:`person_warnings` compares two approvers beyond user id, e-mail and linked
  contact (those still block, D36): contact e-mail addresses, and name plus date of birth of
  the linked contacts. A hit is a **warning** on the decision, never a block, because two
  different persons may share a name (docs/rules/S69-03.md).
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import ApprovalDecision

SUBJECT_TYPES = ("payment_order", "invoice")


# Person features ---------------------------------------------------------------------------


@dataclass
class PersonFeatures:
    user_id: uuid.UUID
    emails: set[str] = field(default_factory=set)
    name: str | None = None
    birth_date: date | None = None


def _norm(text: str | None) -> str | None:
    value = " ".join((text or "").casefold().split())
    return value or None


async def person_features(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> PersonFeatures:
    """E-mail addresses (user and linked contact), name and birth date of the linked contact."""
    from mhvp.contacts.models import Contact, ContactEmail
    from mhvp.platform.models import Membership, User

    out = PersonFeatures(user_id=user_id)
    row = (
        await session.execute(
            select(User.email, User.display_name, Membership.contact_id)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.tenant_id == tenant_id, User.id == user_id)
        )
    ).first()
    if row is None:
        return out
    email, display_name, contact_id = row
    if (value := _norm(email)) is not None:
        out.emails.add(value)
    out.name = _norm(display_name)
    if contact_id is not None:
        contact = await session.get(Contact, contact_id)
        if contact is not None:
            full = _norm(f"{contact.first_name or ''} {contact.last_name or ''}")
            out.name = full or _norm(contact.display_name) or out.name
            out.birth_date = contact.date_of_birth
        for address in (
            await session.scalars(
                select(ContactEmail.email).where(ContactEmail.contact_id == contact_id)
            )
        ).all():
            if (value := _norm(address)) is not None:
                out.emails.add(value)
    return out


def compare(a: PersonFeatures, b: PersonFeatures) -> list[str]:
    """Warnings that ``a`` and ``b`` may be one person with two separate contacts."""
    warnings: list[str] = []
    if a.emails & b.emails:
        warnings.append(
            "Möglicherweise dieselbe Person: gleiche E-Mail-Adresse bei getrennten Kontakten."
        )
    if a.name and a.name == b.name:
        if a.birth_date is not None and b.birth_date is not None:
            if a.birth_date == b.birth_date:
                warnings.append(
                    "Möglicherweise dieselbe Person: gleicher Name und gleiches Geburtsdatum."
                )
        else:
            warnings.append(
                "Möglicherweise dieselbe Person: gleicher Name, Geburtsdatum nicht hinterlegt."
            )
    return warnings


async def person_warnings(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, others: set[uuid.UUID]
) -> list[str]:
    """Warnings of the new approver against every other approver (S69-03). No block."""
    if not others:
        return []
    me = await person_features(session, tenant_id, user_id)
    out: list[str] = []
    for other in sorted(others):
        if other == user_id:
            continue
        for warning in compare(me, await person_features(session, tenant_id, other)):
            if warning not in out:
                out.append(warning)
    return out


# Decisions ---------------------------------------------------------------------------------


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    step: str,
    user_id: uuid.UUID,
    snapshot_hash: str,
    legacy_ref_id: uuid.UUID | None = None,
    warnings: list[str] | None = None,
) -> ApprovalDecision:
    if subject_type not in SUBJECT_TYPES:  # pragma: no cover - programming error
        raise ValueError(subject_type)
    row = ApprovalDecision(
        tenant_id=tenant_id,
        subject_type=subject_type,
        subject_id=subject_id,
        step=step,
        user_id=user_id,
        subject_snapshot_hash=snapshot_hash,
        status="valid",
        legacy_ref_id=legacy_ref_id,
        warnings=list(warnings or []),
    )
    session.add(row)
    await session.flush()
    return row


async def invalidate(
    session: AsyncSession,
    subject_type: str,
    subject_id: uuid.UUID,
    *,
    current_hash: str | None,
    reason: str,
) -> int:
    """Persist ``invalidated`` for every valid decision whose hash differs from
    ``current_hash`` (``None``: all of them). Returns the number of invalidated rows."""
    rows = (
        await session.scalars(
            select(ApprovalDecision).where(
                ApprovalDecision.subject_type == subject_type,
                ApprovalDecision.subject_id == subject_id,
                ApprovalDecision.status == "valid",
            )
        )
    ).all()
    now = datetime.now(UTC)
    count = 0
    for row in rows:
        if current_hash is not None and row.subject_snapshot_hash == current_hash:
            continue
        row.status = "invalidated"
        row.invalidated_at = now
        row.invalidation_reason = reason[:200]
        count += 1
    if count:
        await session.flush()
    return count


async def decisions(
    session: AsyncSession, subject_type: str, subject_id: uuid.UUID
) -> list[ApprovalDecision]:
    return list(
        (
            await session.scalars(
                select(ApprovalDecision)
                .where(
                    ApprovalDecision.subject_type == subject_type,
                    ApprovalDecision.subject_id == subject_id,
                )
                .order_by(ApprovalDecision.decided_at, ApprovalDecision.id)
            )
        ).all()
    )
