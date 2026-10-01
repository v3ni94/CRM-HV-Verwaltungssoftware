"""Magic link login for tenants and owners (M21-01, Masterprompt 14 Portale).

Flow: the portal asks for the e-mail address only (``request_link``); if it belongs to a portal
account, a one time link is mailed (never revealed in the response, rule 0.1.13). Opening the
link (``consume_link``) either issues a session right away, exactly like the existing password
login (``mhvp.core.auth.service.issue_session``), or, when the account switched on the optional
e-mail code second factor, asks for a six digit code mailed separately (``verify_code``). The
existing password login is unaffected and stays available next to this one (task M21-01).

Validity and limits are Produktschutz (a stricter internal standard), not a legal rule
(docs/rules M21-01):

* the link is valid 15 minutes and can be used once;
* the optional e-mail code is valid 10 minutes and can be used once;
* at most ``RATE_LIMIT_PER_HOUR`` requests per e-mail address and per hour are accepted; further
  requests in the same window are silently dropped (the response is identical either way, so the
  endpoint never reveals whether an address has a portal account).

The QR invitation for the printed letter is a separate, longer lived code for account activation
(``mhvp.portal.routers``, ``QR_INVITE_DAYS``), not this login link.

Second factor policy (M2-04, ``mhvp.core.auth.mfa_policy``): when the tenant policy covers the
user (CRM roles by default, portal accounts only with ``portal_required``), the link and the
optional e-mail code do not end the login; the result hands over to TOTP (``mfa_required``) or
to the TOTP setup (``mfa_setup_required``) with a step token for the auth endpoints.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.auth import mfa_policy, tokens
from mhvp.core.auth import service as auth_service
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import User
from mhvp.portal.models import MagicLoginLink, PortalAccount
from mhvp.sla import channels

LINK_TTL_MINUTES = 15
CODE_TTL_MINUTES = 10
RATE_LIMIT_PER_HOUR = 5
RATE_LIMIT_WINDOW_SECONDS = 3600

_log = get_logger("mhvp.portal.magic_link")


@dataclass(frozen=True)
class LinkResult:
    # "code_required", "ok", or (M2-04) "mfa_required" / "mfa_setup_required"
    status: str
    link_id: uuid.UUID | None = None
    issued: auth_service.IssuedTokens | None = None
    # M2-04: step token for /auth/mfa/verify (mfa_required) or /auth/mfa/setup/* (setup).
    step_token: str | None = None


def _hash(secret: str) -> str:
    return tokens.sha256_hex(secret)


def _code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def _rate_limited(redis: Redis, email: str) -> bool:
    """True when the address already used up its hourly quota (fails open on Redis errors,
    like the request rate limit middleware, section 12: availability outranks the limit)."""
    now = int(datetime.now(UTC).timestamp())
    window = now - now % RATE_LIMIT_WINDOW_SECONDS
    key = f"portal:magic:{tokens.sha256_hex(email)}:{window}"
    try:
        count = int(await redis.incr(key))
        if count == 1:
            await redis.expire(key, RATE_LIMIT_WINDOW_SECONDS * 2)
    except (RedisError, OSError):
        _log.warning("magic_link_ratelimit_unavailable")
        return False
    return count > RATE_LIMIT_PER_HOUR


def _login_text(*, portal_url: str | None, link: str) -> tuple[str, str]:
    where = f"unter {link}" if portal_url else f"über den folgenden Link: {link}"
    body = (
        "Guten Tag,\n\n"
        f"mit diesem Link melden Sie sich einmalig im Kundenportal an, {where}\n\n"
        "Der Link ist 15 Minuten gültig und kann nur einmal verwendet werden. Haben Sie die "
        "Anmeldung nicht selbst ausgelöst, ignorieren Sie diese E-Mail bitte.\n\n"
        "Bitte geben Sie den Link nicht an Dritte weiter."
    )
    return "Anmeldelink zum Kundenportal", body


def _code_text(code: str) -> tuple[str, str]:
    body = (
        "Guten Tag,\n\n"
        f"Ihr Bestätigungscode für die Anmeldung lautet: {code}\n\n"
        "Der Code ist 10 Minuten gültig und kann nur einmal verwendet werden. Bitte geben Sie "
        "ihn nicht an Dritte weiter."
    )
    return "Bestätigungscode für die Anmeldung", body


async def request_link(
    session: AsyncSession,
    settings: Settings,
    redis: Redis,
    *,
    tenant_id: uuid.UUID,
    email: str,
    portal_url: str | None,
) -> None:
    """Creates and mails a login link when the address has a portal account (tenant scoped
    ``session``, RLS applies); otherwise does nothing. Always returns ``None`` so the caller
    can answer identically either way (no enumeration, rule 0.1.13)."""
    address = email.strip().lower()
    if not address or await _rate_limited(redis, address):
        return
    user_id = await session.scalar(select(User.id).where(User.email == address))
    if user_id is None:
        return
    account = await session.scalar(
        select(PortalAccount).where(
            PortalAccount.tenant_id == tenant_id, PortalAccount.user_id == user_id
        )
    )
    if account is None or account.status not in ("invited", "active", "locked"):
        return
    secret = tokens.new_opaque_secret()
    session.add(
        MagicLoginLink(
            tenant_id=tenant_id,
            account_id=account.id,
            token_hash=_hash(secret),
            expires_at=datetime.now(UTC) + timedelta(minutes=LINK_TTL_MINUTES),
        )
    )
    await session.flush()
    token = f"{tenant_id.hex}.{secret}"
    link = f"{portal_url.rstrip('/')}/anmeldung/link?token={token}" if portal_url else token
    subject, body = _login_text(portal_url=portal_url, link=link)
    error = await channels.send_email(session, settings, tenant_id, address, subject, body)
    if error:  # pragma: no cover - transport failure, logged without the token
        _log.warning("magic_link_mail_failed", detail=error)


def parse_token(token: str) -> tuple[uuid.UUID, str]:
    try:
        tenant_hex, secret = token.split(".", 1)
        return uuid.UUID(hex=tenant_hex), secret
    except ValueError:
        raise ProblemError(ErrorCodes.MAGIC_LINK_INVALID) from None


async def consume_link(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    redis: Redis,
    *,
    token: str,
    user_agent: str | None,
    portal_url: str | None,
) -> LinkResult:
    """Verifies the link once (single use) and either issues a session right away or, when the
    account requires the e-mail code, mails a code and returns ``code_required``."""
    tenant_id, secret = parse_token(token)
    now = datetime.now(UTC)
    async with tenant_transaction(factory, tenant_id) as session:
        row = await session.scalar(
            select(MagicLoginLink)
            .where(
                MagicLoginLink.tenant_id == tenant_id,
                MagicLoginLink.token_hash == _hash(secret),
            )
            .with_for_update()
        )
        if row is None or row.used_at is not None or row.expires_at < now:
            raise ProblemError(ErrorCodes.MAGIC_LINK_INVALID)
        row.used_at = now
        account = await session.get(PortalAccount, row.account_id)
        if account is None:  # pragma: no cover - FK guarantees this
            raise ProblemError(ErrorCodes.MAGIC_LINK_INVALID)
        user_id = account.user_id
        from mhvp.platform.models import TenantSettings

        tenant_settings = await session.scalar(select(TenantSettings))
        tenant_requires = (
            tenant_settings is not None and tenant_settings.portal_second_factor == "required"
        )
        if account.magic_link_2fa or tenant_requires:
            code = _code()
            row.code_hash = _hash(code)
            row.code_expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
            user = await session.get(User, user_id)
            address = user.email if user is not None else None
            await session.flush()
            link_id = row.id
        else:
            address = None
            link_id = None
    if address is not None:
        async with tenant_transaction(factory, tenant_id) as session:
            subject, body = _code_text(code)
            error = await channels.send_email(session, settings, tenant_id, address, subject, body)
            if error:  # pragma: no cover - transport failure, logged without the code
                _log.warning("magic_link_code_mail_failed", detail=error)
        return LinkResult(status="code_required", link_id=link_id)
    return await _finish(factory, settings, user_id, tenant_id, user_agent)


async def _finish(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_agent: str | None,
) -> LinkResult:
    step = await mfa_policy.policy_step(factory, settings, user_id, tenant_id=tenant_id)
    if step is not None:
        return LinkResult(status=step[0], step_token=step[1])
    issued = await auth_service.issue_session(
        factory, settings, user_id=user_id, tenant_id=tenant_id, user_agent=user_agent
    )
    await auth_service.record_login(factory, user_id)
    return LinkResult(status="ok", issued=issued)


async def verify_code(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    link_id: uuid.UUID,
    code: str,
    user_agent: str | None,
) -> auth_service.IssuedTokens:
    """Like ``verify_code_step`` for callers that expect a session; refuses (MHVP-AUTH-0015)
    when the second factor policy demands a further step, so it is never a way around it."""
    result = await verify_code_step(
        factory, settings, tenant_id=tenant_id, link_id=link_id, code=code, user_agent=user_agent
    )
    if result.issued is None:
        raise ProblemError(ErrorCodes.MFA_REQUIRED_BY_POLICY)
    return result.issued


async def verify_code_step(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    link_id: uuid.UUID,
    code: str,
    user_agent: str | None,
) -> LinkResult:
    now = datetime.now(UTC)
    async with tenant_transaction(factory, tenant_id) as session:
        row = await session.scalar(
            select(MagicLoginLink)
            .where(MagicLoginLink.tenant_id == tenant_id, MagicLoginLink.id == link_id)
            .with_for_update()
        )
        if (
            row is None
            or row.used_at is None  # the link itself must have been consumed first
            or row.code_hash is None
            or row.code_used_at is not None
            or row.code_expires_at is None
            or row.code_expires_at < now
            or not tokens.constant_time_equals(row.code_hash, _hash(code.strip()))
        ):
            raise ProblemError(ErrorCodes.MAGIC_LINK_INVALID)
        row.code_used_at = now
        account = await session.get(PortalAccount, row.account_id)
        if account is None:  # pragma: no cover - FK guarantees this
            raise ProblemError(ErrorCodes.MAGIC_LINK_INVALID)
        user_id = account.user_id
    return await _finish(factory, settings, user_id, tenant_id, user_agent)
