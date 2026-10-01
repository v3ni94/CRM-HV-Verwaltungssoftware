"""Second factor obligation per role as a tenant policy (section 3.4, M2-04, M21-09).

Section 3.4 asks for a mandatory TOTP second factor for management roles (Verwaltungsrollen);
section 14 keeps it optional in the customer portal. The operator decision M2-01 (26.09.2026)
made TOTP voluntary for everyone and stays the default; wave 16 (priority list 01.10.2026,
item 25) turns the obligation into a tenant choice with three CRM modes:

- ``voluntary`` (default, also without a policy row): the M2-01 behaviour, every user decides
  alone. Nobody is forced to set up a factor by this feature.
- ``all_staff``: every membership holding any role other than ``portal_user`` (system or
  custom role) must use a second factor.
- ``roles``: only the role codes listed in ``crm_role_codes``.

``portal_required`` (default false) extends the obligation to the portal role ``portal_user``.

Transition (no lockout): the policy takes effect at the next login. A user who falls under it
and has no second factor yet (neither TOTP nor a passkey) gets ``mfa_setup_required`` with a
short lived setup token instead of a session and sets up TOTP inside the login flow; running
sessions are not ended. A passkey counts as second factor (A-U04-01). The policy only adds
checks; it never removes the existing voluntary second factor or the trusted device rule.

A user is global while policies are per tenant: one active membership whose roles fall under
its tenant's policy makes the second factor mandatory for the user (the stricter answer wins).
Fachliche Umsetzung of 3.4; the default follows the operator decision M2-01 (coordinator
decision 01.10.2026), the obligation is a tenant choice, not a legal rule (docs/rules/M2-04.md).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth import tokens, webauthn
from mhvp.core.config import Settings
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.platform.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Role,
    User,
    WebAuthnCredential,
)

PORTAL_ROLE_CODE = "portal_user"
CRM_MODES: tuple[str, ...] = ("all_staff", "roles", "voluntary")
DEFAULT_CRM_MODE = "voluntary"


class AuthMfaPolicy(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant second factor policy (migration 0383). No row means the default policy."""

    __tablename__ = "auth_mfa_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("crm_mode IN ('all_staff', 'roles', 'voluntary')", name="crm_mode_values"),
    )

    crm_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_CRM_MODE, server_default=DEFAULT_CRM_MODE
    )
    crm_role_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    portal_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


@dataclass(frozen=True, slots=True)
class MfaPolicy:
    crm_mode: str = DEFAULT_CRM_MODE
    crm_role_codes: tuple[str, ...] = ()
    portal_required: bool = False
    stored: bool = False


DEFAULT_POLICY = MfaPolicy()


def requires_second_factor(policy: MfaPolicy, role_codes: list[str] | tuple[str, ...]) -> bool:
    """Pure rule: does a membership with these direct role codes need a second factor?"""
    codes = set(role_codes)
    staff = codes - {PORTAL_ROLE_CODE}
    if staff:
        if policy.crm_mode == "all_staff":
            return True
        if policy.crm_mode == "roles" and staff & set(policy.crm_role_codes):
            return True
    return PORTAL_ROLE_CODE in codes and policy.portal_required


def _policy_of(row: AuthMfaPolicy | None) -> MfaPolicy:
    if row is None:
        return DEFAULT_POLICY
    mode = row.crm_mode if row.crm_mode in CRM_MODES else DEFAULT_CRM_MODE
    return MfaPolicy(
        crm_mode=mode,
        crm_role_codes=tuple(sorted({str(c) for c in row.crm_role_codes or []})),
        portal_required=bool(row.portal_required),
        stored=True,
    )


async def load_policy(session: AsyncSession) -> MfaPolicy:
    """Policy of the tenant bound to ``session`` (tenant transaction, RLS)."""
    return _policy_of(await session.scalar(select(AuthMfaPolicy)))


async def store_policy(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    crm_mode: str,
    crm_role_codes: list[str],
    portal_required: bool,
) -> MfaPolicy:
    """Creates or replaces the policy and records the change (event with old and new values)."""
    row = await session.scalar(select(AuthMfaPolicy).with_for_update())
    before = _policy_of(row)
    codes = sorted({c.strip() for c in crm_role_codes if c.strip()})
    if row is None:
        row = AuthMfaPolicy(tenant_id=tenant_id, created_by=actor_user_id)
        session.add(row)
    row.crm_mode = crm_mode
    row.crm_role_codes = codes
    row.portal_required = portal_required
    row.updated_by = actor_user_id
    await session.flush()
    after = _policy_of(row)
    await emit(
        session,
        tenant_id=tenant_id,
        type="auth.mfa_policy_changed",
        entity_type="auth_mfa_policy",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        payload={"before": _payload(before), "after": _payload(after)},
    )
    return after


def _payload(policy: MfaPolicy) -> dict[str, Any]:
    return {
        "crm_mode": policy.crm_mode,
        "crm_role_codes": list(policy.crm_role_codes),
        "portal_required": policy.portal_required,
    }


async def membership_role_codes(session: AsyncSession, membership_id: uuid.UUID) -> list[str]:
    return sorted(
        await session.scalars(
            select(Role.code)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(MembershipRole.membership_id == membership_id)
        )
    )


async def user_requires_second_factor(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> bool:
    """True when any active membership of the user falls under its tenant's policy."""
    async with platform_transaction(factory) as session:
        memberships = (
            await session.execute(
                select(Membership.id, Membership.tenant_id).where(
                    Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE
                )
            )
        ).all()
    for membership_id, tenant_id in memberships:
        async with tenant_transaction(factory, tenant_id) as session:
            policy = await load_policy(session)
            codes = await membership_role_codes(session, membership_id)
        if requires_second_factor(policy, codes):
            return True
    return False


async def policy_step(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    user_id: uuid.UUID,
    *,
    tenant_id: uuid.UUID | None,
) -> tuple[str, str] | None:
    """Login paths that otherwise need no TOTP (magic link, M21-01): when the policy covers the
    user, returns ``("mfa_required", mfa_token)`` for a user with a second factor or
    ``("mfa_setup_required", setup_token)`` for one without; ``None`` leaves the path as is."""
    if not await user_requires_second_factor(factory, user_id):
        return None
    async with platform_transaction(factory) as session:
        user = await session.get(User, user_id)
        totp_enabled = bool(user is not None and user.totp_enabled)
        passkey = await session.scalar(
            select(WebAuthnCredential.id)
            .where(WebAuthnCredential.user_id == user_id, WebAuthnCredential.revoked_at.is_(None))
            .limit(1)
        )
    if totp_enabled or (passkey is not None and webauthn.is_available(settings)):
        return "mfa_required", tokens.issue_mfa_token(settings, user_id, tenant_id=tenant_id)
    return "mfa_setup_required", tokens.issue_mfa_setup_token(
        settings, user_id, tenant_id=tenant_id
    )
