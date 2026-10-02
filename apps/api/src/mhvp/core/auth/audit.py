"""Security audit events of the login flow (GAH-302, section 16, 12 Audit).

Users and sessions are platform rows, while the audit trail (``domain_event``) is tenant
bound under RLS. Every security event of a user is therefore recorded once in each tenant the
user is an active member of (or only in the named tenant), in a separate tenant transaction
after the login transaction. A failed login for an unknown email has no tenant and is not
recorded (only the rate limit applies). Payloads never contain passwords, codes, tokens or
secrets; ``emit`` redacts on top.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.platform.models import Membership, MembershipStatus

LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
ACCOUNT_LOCKED = "auth.account_locked"
PASSWORD_CHANGED = "auth.password_changed"
TOTP_ENABLED = "auth.totp_enabled"
TOTP_DISABLED = "auth.totp_disabled"
PASSKEY_REGISTERED = "auth.passkey_registered"
PASSKEY_REVOKED = "auth.passkey_revoked"
SESSION_REVOKED = "auth.session_revoked"
TRUSTED_DEVICE_REVOKED = "auth.trusted_device_revoked"
OIDC_TOKEN_ISSUED = "auth.oidc_token_issued"
MFA_RESET = "auth.mfa_reset"

SECURITY_EVENT_TYPES = (
    LOGIN_SUCCEEDED,
    LOGIN_FAILED,
    ACCOUNT_LOCKED,
    PASSWORD_CHANGED,
    TOTP_ENABLED,
    TOTP_DISABLED,
    PASSKEY_REGISTERED,
    PASSKEY_REVOKED,
    SESSION_REVOKED,
    TRUSTED_DEVICE_REVOKED,
    OIDC_TOKEN_ISSUED,
    MFA_RESET,
)

# Keys that must never reach a security event payload (defence in depth beside ``redact``).
_FORBIDDEN_KEYS = frozenset(
    {"password", "current_password", "new_password", "code", "secret", "token", "totp_secret"}
)


async def _active_tenants(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[uuid.UUID]:
    async with platform_transaction(factory) as session:
        rows = await session.scalars(
            select(Membership.tenant_id).where(
                Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE
            )
        )
        return sorted(set(rows.all()))


async def record(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    type: str,
    actor_user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    """Records ``type`` for ``user_id``; returns the number of tenants it was written to."""
    if type not in SECURITY_EVENT_TYPES:
        raise ValueError(f"unknown security event type {type!r}")
    clean = {k: v for k, v in (payload or {}).items() if k not in _FORBIDDEN_KEYS}
    tenants = [tenant_id] if tenant_id is not None else await _active_tenants(factory, user_id)
    for tid in tenants:
        async with tenant_transaction(factory, tid) as session:
            await emit(
                session,
                tenant_id=tid,
                type=type,
                entity_type="user",
                entity_id=user_id,
                actor_user_id=actor_user_id if actor_user_id is not None else user_id,
                payload=clean,
            )
    return len(tenants)
