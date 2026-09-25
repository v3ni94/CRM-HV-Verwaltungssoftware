"""Login, MFA, token sessions and tenant switch (section 3.4)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core import crypto
from mhvp.core.auth import passwords, tokens, totp
from mhvp.core.auth.permissions import effective_permissions
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import (
    Membership,
    MembershipStatus,
    RefreshToken,
    Tenant,
    TrustedDevice,
    User,
)

# Roles for which TOTP stays mandatory (operator 25.09.2026, ADR 0006 addendum). Other users
# log in with password only unless they enable TOTP themselves under "Meine Daten".
ADMIN_ROLE_CODES: frozenset[str] = frozenset({"tenant_admin", "administrator"})
TRUSTED_DEVICE_TTL_DAYS = 180


@dataclass(frozen=True)
class TenantRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int
    tenant_id: uuid.UUID | None
    tenants: list[TenantRef]


def ensure_configured(settings: Settings) -> None:
    if settings.jwt_private_key is None or not crypto.is_configured():
        raise ProblemError(ErrorCodes.AUTH_NOT_CONFIGURED)
    try:
        tokens.public_jwk(settings)
    except tokens.TokenError:
        raise ProblemError(ErrorCodes.AUTH_NOT_CONFIGURED) from None


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def _register_failure(session: AsyncSession, user: User, now: datetime) -> None:
    user.failed_logins += 1
    if user.failed_logins >= passwords.MAX_FAILED_LOGINS:
        user.locked_until = now + timedelta(minutes=passwords.LOCKOUT_MINUTES)
        user.failed_logins = 0
    await session.flush()


async def check_password(
    factory: async_sessionmaker[AsyncSession], email: str, password: str
) -> tuple[uuid.UUID, bool]:
    """Returns (user id, totp enabled). Failures count towards the lockout."""
    now = datetime.now(UTC)
    async with platform_transaction(factory) as session:
        user = await session.scalar(select(User).where(User.email == normalise_email(email)))
        if user is None:
            passwords.verify_password(None, password)  # equalise timing
            raise ProblemError(ErrorCodes.INVALID_CREDENTIALS)
        if user.locked_until is not None and user.locked_until > now:
            raise ProblemError(ErrorCodes.ACCOUNT_LOCKED)
        if not user.active or not passwords.verify_password(user.password_hash, password):
            await _register_failure(session, user, now)
            failure = ProblemError(ErrorCodes.INVALID_CREDENTIALS)
        else:
            failure = None
            user.failed_logins = 0
            if user.password_hash and passwords.needs_rehash(user.password_hash):
                user.password_hash = passwords.hash_password(password)
            result = (user.id, user.totp_enabled)
    if failure is not None:
        raise failure
    return result


async def start_totp_setup(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> tuple[str, str]:
    async with platform_transaction(factory) as session:
        user = await session.get(User, user_id)
        if user is None or not user.active:
            raise ProblemError(ErrorCodes.INVALID_CREDENTIALS)
        if user.totp_enabled:
            raise ProblemError(ErrorCodes.CONFLICT, developer_message="TOTP already enabled.")
        secret = totp.new_secret()
        user.totp_secret = secret
        return secret, totp.provisioning_uri(secret, user.email)


async def verify_totp(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, code: str
) -> None:
    now = datetime.now(UTC)
    async with platform_transaction(factory) as session:
        user = await session.get(User, user_id)
        if user is None or not user.active:
            raise ProblemError(ErrorCodes.INVALID_CREDENTIALS)
        if user.locked_until is not None and user.locked_until > now:
            raise ProblemError(ErrorCodes.ACCOUNT_LOCKED)
        step = (
            totp.matching_step(user.totp_secret, code, last_step=user.totp_last_step)
            if user.totp_secret
            else None
        )
        if step is None:
            await _register_failure(session, user, now)
            failure: ProblemError | None = ProblemError(ErrorCodes.INVALID_CREDENTIALS)
        else:
            failure = None
            user.totp_last_step = step
            user.totp_enabled = True
            user.failed_logins = 0
            user.last_login_at = now
    if failure is not None:
        raise failure


async def memberships(session: AsyncSession, user_id: uuid.UUID) -> list[TenantRef]:
    rows = await session.execute(
        select(Tenant.id, Tenant.name)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Tenant.name)
    )
    return [TenantRef(id=row.id, name=row.name) for row in rows]


async def totp_mandatory(factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> bool:
    """TOTP is mandatory for platform administrators and for a tenant_admin/administrator
    membership in any tenant (operator 25.09.2026). Everyone else may log in with password
    only, unless they already enabled TOTP themselves."""
    async with platform_transaction(factory) as session:
        user = await session.get(User, user_id)
        if user is None:
            return True
        if user.is_platform_admin:
            return True
        rows = (
            await session.execute(
                select(Membership.tenant_id, Membership.id).where(
                    Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE
                )
            )
        ).all()
    for row in rows:
        async with tenant_transaction(factory, row.tenant_id) as session:
            _, codes = await effective_permissions(session, row.tenant_id, row.id)
        if ADMIN_ROLE_CODES.intersection(codes):
            return True
    return False


async def store_trusted_device(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    raw_token: str,
    user_agent: str | None,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    async with platform_transaction(factory) as session:
        session.add(
            TrustedDevice(
                user_id=user_id,
                tenant_id=tenant_id,
                token_hash=tokens.sha256_hex(raw_token),
                label=(user_agent or "")[:300] or None,
                expires_at=now + timedelta(days=TRUSTED_DEVICE_TTL_DAYS),
            )
        )


async def check_trusted_device(
    factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    raw_token: str,
    now: datetime | None = None,
) -> bool:
    """Validates a device token for exactly this user and touches ``last_used_at``. A token
    issued to another user is rejected even if it is otherwise valid (no cross-user reuse)."""
    now = now or datetime.now(UTC)
    async with platform_transaction(factory) as session:
        device = await session.scalar(
            select(TrustedDevice).where(TrustedDevice.token_hash == tokens.sha256_hex(raw_token))
        )
        if (
            device is None
            or device.user_id != user_id
            or device.revoked_at is not None
            or device.expires_at <= now
        ):
            return False
        device.last_used_at = now
        return True


async def list_trusted_devices(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> list[TrustedDevice]:
    now = datetime.now(UTC)
    async with platform_transaction(factory) as session:
        rows = await session.execute(
            select(TrustedDevice)
            .where(
                TrustedDevice.user_id == user_id,
                TrustedDevice.revoked_at.is_(None),
                TrustedDevice.expires_at > now,
            )
            .order_by(TrustedDevice.created_at.desc())
        )
        return list(rows.scalars())


async def revoke_trusted_device(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, device_id: uuid.UUID
) -> bool:
    async with platform_transaction(factory) as session:
        result = await session.execute(
            update(TrustedDevice)
            .where(
                TrustedDevice.id == device_id,
                TrustedDevice.user_id == user_id,
                TrustedDevice.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def revoke_all_trusted_devices(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Revokes every trusted device of a user (password reset by an admin, TOTP secret reset)."""
    async with platform_transaction(factory) as session:
        await session.execute(
            update(TrustedDevice)
            .where(TrustedDevice.user_id == user_id, TrustedDevice.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )


async def _roles(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[str]:
    async with platform_transaction(factory) as session:
        membership_id = await session.scalar(
            select(Membership.id).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
    if membership_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No membership in tenant.")
    async with tenant_transaction(factory, tenant_id) as session:
        _, roles = await effective_permissions(session, tenant_id, membership_id)
    return roles


async def issue_session(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    user_agent: str | None,
    family_id: uuid.UUID | None = None,
) -> IssuedTokens:
    async with platform_transaction(factory) as session:
        tenants = await memberships(session, user_id)
    if tenant_id is None and len(tenants) == 1:
        tenant_id = tenants[0].id
    if tenant_id is not None and tenant_id not in {t.id for t in tenants}:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No membership in tenant.")
    roles = await _roles(factory, tenant_id, user_id) if tenant_id else []
    now = datetime.now(UTC)
    refresh = tokens.new_opaque_secret()
    async with platform_transaction(factory) as session:
        session.add(
            RefreshToken(
                user_id=user_id,
                family_id=family_id or uuid.uuid4(),
                token_hash=tokens.sha256_hex(refresh),
                tenant_id=tenant_id,
                user_agent=(user_agent or "")[:300] or None,
                issued_at=now,
                expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            )
        )
    access = tokens.issue_access_token(
        settings, tokens.AccessClaims(user_id=user_id, tenant_id=tenant_id, roles=roles), now=now
    )
    return IssuedTokens(access, refresh, settings.access_token_ttl_seconds, tenant_id, tenants)


async def rotate_refresh(
    factory: async_sessionmaker[AsyncSession], settings: Settings, raw: str, user_agent: str | None
) -> IssuedTokens:
    now = datetime.now(UTC)
    async with platform_transaction(factory) as session:
        token = await session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == tokens.sha256_hex(raw))
            .with_for_update()
        )
        if token is None:
            raise ProblemError(ErrorCodes.REFRESH_INVALID)
        if token.used_at is not None or token.revoked_at is not None:
            # Reuse of a rotated token: the family is compromised, end the session.
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            reused = True
        else:
            reused = False
            if token.expires_at <= now:
                raise ProblemError(ErrorCodes.REFRESH_INVALID)
            token.used_at = now
            user = await session.get(User, token.user_id)
            if user is None or not user.active:
                raise ProblemError(ErrorCodes.REFRESH_INVALID)
            user_id, tenant_id, family_id = token.user_id, token.tenant_id, token.family_id
    if reused:
        raise ProblemError(ErrorCodes.REFRESH_INVALID)
    try:
        return await issue_session(
            factory,
            settings,
            user_id=user_id,
            tenant_id=tenant_id,
            user_agent=user_agent,
            family_id=family_id,
        )
    except ProblemError:
        raise ProblemError(ErrorCodes.REFRESH_INVALID) from None


async def revoke_family(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, family_id: uuid.UUID
) -> bool:
    async with platform_transaction(factory) as session:
        result = await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]


async def family_of(
    factory: async_sessionmaker[AsyncSession], raw: str
) -> tuple[uuid.UUID, uuid.UUID] | None:
    async with platform_transaction(factory) as session:
        row = (
            await session.execute(
                select(RefreshToken.user_id, RefreshToken.family_id).where(
                    RefreshToken.token_hash == tokens.sha256_hex(raw)
                )
            )
        ).first()
    return (row.user_id, row.family_id) if row else None


async def platform_switch(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    admin_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str,
) -> IssuedTokens:
    """Explicit, recorded access of a platform administrator to a tenant (5.1)."""
    async with platform_transaction(factory) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    async with tenant_transaction(factory, tenant_id) as session:
        await emit(
            session,
            tenant_id=tenant_id,
            type="platform.tenant_switched",
            entity_type="tenant",
            entity_id=tenant_id,
            actor_user_id=admin_id,
            payload={"reason": reason},
        )
    access = tokens.issue_access_token(
        settings,
        tokens.AccessClaims(
            user_id=admin_id, tenant_id=tenant_id, platform=True, platform_access_reason=reason
        ),
    )
    # No refresh token: platform access ends with the short lived access token.
    return IssuedTokens(
        access,
        None,
        settings.access_token_ttl_seconds,
        tenant_id,
        [TenantRef(tenant.id, tenant.name)],
    )
