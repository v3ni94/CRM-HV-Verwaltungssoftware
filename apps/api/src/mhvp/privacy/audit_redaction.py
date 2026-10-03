"""Audit trail without clear text after a contact erasure (GAM-401, AP13).

Tenant switch ``privacy.audit_redaction`` in ``tenant_settings.sources`` (default off, which is
the behaviour before AP13: ``audit_log.changes`` keeps old and new values). When on, the
anonymisation of a contact (execution and journal replay after a restore) reduces every
``audit_log`` row with ``entity_type='contact'`` and the contact's id to the field names; each
value becomes ``{"redacted": true}``. Whether field names without values remain sufficient
evidence is open (OPEN_QUESTIONS AP13-01).

The table stays append only: migration 0465 allows exactly this update (database function
``audit_redact_changes``, row trigger ``audit_log_redact_only``); deletes, truncates and any
other update are refused by the database. Domain events, postings and other evidence are not
touched (B03, retention holds).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

SWITCH_KEY = "privacy.audit_redaction"
REDACTED_VALUE: dict[str, bool] = {"redacted": True}
REDACTED_ENTITY_TYPES: tuple[str, ...] = ("contact",)


def enabled_from(sources: dict[str, Any] | None) -> bool:
    return bool((sources or {}).get(SWITCH_KEY) is True)


async def is_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    return enabled_from(await session.scalar(select(TenantSettings.sources)))


def redacted(changes: dict[str, Any]) -> dict[str, Any]:
    """Python twin of the database function (for tests and previews)."""
    return {key: dict(REDACTED_VALUE) for key in changes}


async def redact_contact_audit(session: AsyncSession, contact_id: uuid.UUID) -> int:
    """Reduces the audit rows of the contact to field names; returns the number of rows."""
    res = await session.execute(
        text(
            "UPDATE audit_log SET changes = audit_redact_changes(changes) "
            "WHERE entity_type = ANY(:types) AND entity_id = :cid "
            "AND changes IS DISTINCT FROM audit_redact_changes(changes)"
        ),
        {"types": list(REDACTED_ENTITY_TYPES), "cid": contact_id},
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]
