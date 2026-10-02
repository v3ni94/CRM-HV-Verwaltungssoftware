"""Reset of a lost second factor by the tenant administrator, four eyes (GAH-301, AI09-01).

Variant "Admin-Zurücksetzen" of the open decision AI09-01 (recovery codes, admin reset or
both). Technically prepared behind the tenant switch ``mfa_admin_reset_enabled`` (default
off, table ``auth_mfa_reset_setting``, migration 0442). With the switch on, one member with
``members:update`` files a request (``auth_mfa_reset_request``), a second, different member
with ``members:update`` approves it. Only the approval resets: TOTP off and secret removed,
every passkey revoked, every trusted device and every refresh token of the user revoked. The
user then signs in with the password; a tenant policy that requires a second factor leads to
the setup step in the login flow (M2-04). Identity proof of the user stays an organisational
duty of the administrators (reason is mandatory). Every step is recorded as domain event, the
reset additionally as ``auth.mfa_reset`` and notified to the user and the requester.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth import audit
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.auth.service import revoke_all_trusted_devices
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Membership, RefreshToken, User, WebAuthnCredential

SWITCH = "mfa_admin_reset_enabled"
STATUSES = ("requested", "approved", "rejected")


class AuthMfaResetSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant switch ``mfa_admin_reset_enabled`` (no row: off)."""

    __tablename__ = "auth_mfa_reset_setting"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class AuthMfaResetRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Four eyes request to reset the second factor of a member."""

    __tablename__ = "auth_mfa_reset_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'approved', 'rejected')", name="auth_mfa_reset_status"
        ),
        Index("ix_auth_mfa_reset_request_tenant", "tenant_id", "created_at"),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("membership.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", server_default="requested"
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class AuthMfaResetSettingOut(BaseModel):
    enabled: bool


class AuthMfaResetSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class AuthMfaResetRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=2000)


class AuthMfaResetDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=2000)


class AuthMfaResetRequestOut(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    target_user_id: uuid.UUID
    reason: str
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_comment: str | None = None
    created_at: datetime


router = APIRouter(prefix="/auth/mfa-reset", tags=["Anmeldung"])


def _out(row: AuthMfaResetRequest) -> AuthMfaResetRequestOut:
    return AuthMfaResetRequestOut(
        id=row.id,
        membership_id=row.membership_id,
        target_user_id=row.target_user_id,
        reason=row.reason,
        status=row.status,
        requested_by=row.requested_by,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        decision_comment=row.decision_comment,
        created_at=row.created_at,
    )


async def _enabled(session: AsyncSession) -> bool:
    row = await session.scalar(select(AuthMfaResetSetting))
    return bool(row is not None and row.enabled)


@router.get(
    "/settings",
    summary="Schalter Zurücksetzen zweiter Faktor (GAH-301)",
    dependencies=[Depends(strict_query)],
)
async def get_mfa_reset_setting(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> AuthMfaResetSettingOut:
    async with tenant_tx(request, principal) as session:
        return AuthMfaResetSettingOut(enabled=await _enabled(session))


@router.put("/settings", summary="Schalter Zurücksetzen zweiter Faktor ändern (GAH-301)")
async def put_mfa_reset_setting(
    body: AuthMfaResetSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> AuthMfaResetSettingOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(AuthMfaResetSetting).with_for_update())
        before = bool(row is not None and row.enabled)
        if row is None:
            row = AuthMfaResetSetting(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        row.enabled = body.enabled
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="auth.mfa_reset_setting_changed",
            entity_type="auth_mfa_reset_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"switch": SWITCH, "before": before, "after": body.enabled},
        )
    return AuthMfaResetSettingOut(enabled=body.enabled)


@router.get(
    "/requests", summary="Anträge Zurücksetzen zweiter Faktor", dependencies=[Depends(strict_query)]
)
async def list_mfa_reset_requests(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> list[AuthMfaResetRequestOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(AuthMfaResetRequest).order_by(AuthMfaResetRequest.created_at.desc()).limit(200)
        )
        return [_out(r) for r in rows]


@router.post("/requests", status_code=201, summary="Zurücksetzen zweiter Faktor beantragen")
async def create_mfa_reset_request(
    body: AuthMfaResetRequestIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> AuthMfaResetRequestOut:
    async with platform_transaction(sessions(request)) as session:
        membership = await session.get(Membership, body.membership_id)
        if membership is None or membership.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        target_user_id = membership.user_id
    if target_user_id == principal.user_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Den eigenen zweiten Faktor bitte selbst verwalten."
        )
    async with tenant_tx(request, principal) as session:
        if not await _enabled(session):
            raise ProblemError(ErrorCodes.MFA_RESET_DISABLED)
        open_row = await session.scalar(
            select(AuthMfaResetRequest.id).where(
                AuthMfaResetRequest.membership_id == body.membership_id,
                AuthMfaResetRequest.status == "requested",
            )
        )
        if open_row is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Es gibt bereits einen offenen Antrag.")
        row = AuthMfaResetRequest(
            tenant_id=principal.tenant_id,
            membership_id=body.membership_id,
            target_user_id=target_user_id,
            reason=body.reason.strip(),
            requested_by=principal.user_id,
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="auth.mfa_reset_requested",
            entity_type="auth_mfa_reset_request",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"membership_id": str(body.membership_id)},
        )
        return _out(row)


async def _open_request(session: AsyncSession, request_id: uuid.UUID) -> AuthMfaResetRequest:
    row = await session.scalar(
        select(AuthMfaResetRequest).where(AuthMfaResetRequest.id == request_id).with_for_update()
    )
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status != "requested":
        raise ProblemError(ErrorCodes.MFA_RESET_STATE)
    return row


async def _reset_factors(request: Request, user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, user_id)
        if user is None:  # pragma: no cover - membership references the user
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        user.totp_enabled = False
        user.totp_secret = None
        user.totp_last_step = None
        user.failed_logins = 0
        user.locked_until = None
        await session.execute(
            update(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user_id, WebAuthnCredential.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    await revoke_all_trusted_devices(sessions(request), user_id)


@router.post("/requests/{request_id}/approve", summary="Zurücksetzen zweiter Faktor freigeben")
async def approve_mfa_reset_request(
    request_id: uuid.UUID,
    body: AuthMfaResetDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> AuthMfaResetRequestOut:
    async with tenant_tx(request, principal) as session:
        if not await _enabled(session):
            raise ProblemError(ErrorCodes.MFA_RESET_DISABLED)
        row = await _open_request(session, request_id)
        if row.requested_by == principal.user_id:
            raise ProblemError(ErrorCodes.MFA_RESET_FOUR_EYES)
        if row.target_user_id == principal.user_id:
            raise ProblemError(ErrorCodes.MFA_RESET_FOUR_EYES)
        target, requester = row.target_user_id, row.requested_by
    await _reset_factors(request, target)
    from mhvp.workspace.services import notify

    async with tenant_tx(request, principal) as session:
        row = await _open_request(session, request_id)
        row.status = "approved"
        row.decided_by = principal.user_id
        row.decided_at = datetime.now(UTC)
        row.decision_comment = (body.comment or "").strip() or None
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="auth.mfa_reset_approved",
            entity_type="auth_mfa_reset_request",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"membership_id": str(row.membership_id), "requested_by": str(requester)},
        )
        for uid, title in (
            (target, "Ihr zweiter Faktor wurde zurückgesetzt. Bitte neu einrichten."),
            (requester, "Antrag freigegeben: zweiter Faktor wurde zurückgesetzt."),
        ):
            await notify(
                session,
                tenant_id=principal.tenant_id,
                user_id=uid,
                kind="auth.mfa_reset",
                title=title,
                entity_type="auth_mfa_reset_request",
                entity_id=row.id,
            )
        out = _out(row)
    await audit.record(
        sessions(request),
        user_id=target,
        type=audit.MFA_RESET,
        actor_user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        payload={"request_id": str(request_id), "requested_by": str(requester)},
    )
    return out


@router.post("/requests/{request_id}/reject", summary="Zurücksetzen zweiter Faktor ablehnen")
async def reject_mfa_reset_request(
    request_id: uuid.UUID,
    body: AuthMfaResetDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("members:update")),
) -> AuthMfaResetRequestOut:
    async with tenant_tx(request, principal) as session:
        row = await _open_request(session, request_id)
        row.status = "rejected"
        row.decided_by = principal.user_id
        row.decided_at = datetime.now(UTC)
        row.decision_comment = (body.comment or "").strip() or None
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="auth.mfa_reset_rejected",
            entity_type="auth_mfa_reset_request",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"membership_id": str(row.membership_id)},
        )
        return _out(row)
