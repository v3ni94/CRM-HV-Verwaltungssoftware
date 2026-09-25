"""Auth endpoints (/api/v1/auth)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from mhvp.core.auth import passwords, service, tokens
from mhvp.core.auth.principal import Principal, get_principal, sessions
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import RefreshToken, User

router = APIRouter(prefix="/auth", tags=["Anmeldung"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    # Token eines vertrauenswürdigen Geräts (180 Tage): überspringt nur den TOTP-Schritt.
    device_token: str | None = Field(default=None, max_length=4096)


class MfaTokenRequest(BaseModel):
    mfa_token: str


class MfaSetup(BaseModel):
    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)
    tenant_id: uuid.UUID | None = None
    remember_device: bool = False


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str | None
    tenant_id: uuid.UUID | None
    tenants: list[TenantOut]
    # Nur nach mfa/verify mit remember_device gesetzt (vertrautes Gerät, 180 Tage).
    device_token: str | None = None


class LoginStep(BaseModel):
    status: str = Field(description="ok, mfa_required oder mfa_setup_required")
    mfa_token: str | None = None
    # Bei status "ok" (kein zweiter Faktor nötig oder Gerät vertraut) direkt die Sitzung.
    tokens: TokenResponse | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SwitchRequest(BaseModel):
    tenant_id: uuid.UUID
    reason: str | None = Field(
        default=None, max_length=500, description="Pflicht für Plattformzugriff ohne Mitgliedschaft"
    )


class SessionOut(BaseModel):
    family_id: uuid.UUID
    tenant_id: uuid.UUID | None
    user_agent: str | None
    started_at: datetime
    last_used_at: datetime


class MeOut(BaseModel):
    user_id: uuid.UUID | None
    email: str | None
    display_name: str | None
    tenant_id: uuid.UUID | None
    roles: list[str]
    permissions: list[str]
    is_platform_admin: bool
    platform_access_reason: str | None


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    service.ensure_configured(settings)
    return settings


def _out(issued: service.IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token,
        tenant_id=issued.tenant_id,
        tenants=[TenantOut(id=t.id, name=t.name) for t in issued.tenants],
    )


def _mfa_user(settings: Settings, token: str) -> uuid.UUID:
    try:
        return tokens.decode_mfa_token(settings, token)
    except (tokens.TokenError, ValueError, KeyError):
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED) from None


async def _login_ok(request: Request, settings: Settings, user_id: uuid.UUID) -> LoginStep:
    issued = await service.issue_session(
        sessions(request),
        settings,
        user_id=user_id,
        tenant_id=None,
        user_agent=request.headers.get("user-agent"),
    )
    return LoginStep(status="ok", tokens=_out(issued))


@router.post("/login", summary="Anmeldung Schritt 1: E-Mail und Passwort")
async def login(body: LoginRequest, request: Request) -> LoginStep:
    settings = _settings(request)
    user_id, totp_enabled = await service.check_password(
        sessions(request), body.email, body.password
    )
    if totp_enabled:
        # Vertrautes Gerät (180 Tage): nur der TOTP-Schritt entfällt, nie das Passwort.
        # Der Fingerabdruck bindet das Token an das aktuelle TOTP-Geheimnis.
        if body.device_token:
            try:
                device_user, fingerprint = tokens.decode_device_token(settings, body.device_token)
            except (tokens.TokenError, ValueError, KeyError):
                device_user, fingerprint = None, ""
            if device_user == user_id:
                expected = await service.device_fingerprint(sessions(request), user_id)
                if expected is not None and fingerprint == expected:
                    return await _login_ok(request, settings, user_id)
        return LoginStep(status="mfa_required", mfa_token=tokens.issue_mfa_token(settings, user_id))
    # 2FA-Pflicht gilt nur für Administratoren; alle anderen melden sich direkt an.
    if await service.requires_mfa(sessions(request), user_id):
        return LoginStep(
            status="mfa_setup_required", mfa_token=tokens.issue_mfa_token(settings, user_id)
        )
    return await _login_ok(request, settings, user_id)


@router.post("/mfa/setup", summary="Zweiten Faktor (TOTP) einrichten")
async def mfa_setup(body: MfaTokenRequest, request: Request) -> MfaSetup:
    settings = _settings(request)
    secret, uri = await service.start_totp_setup(
        sessions(request), _mfa_user(settings, body.mfa_token)
    )
    return MfaSetup(secret=secret, otpauth_uri=uri)


@router.post("/mfa/verify", summary="Anmeldung Schritt 2: TOTP-Code, Token ausstellen")
async def mfa_verify(body: MfaVerifyRequest, request: Request) -> TokenResponse:
    settings = _settings(request)
    user_id = _mfa_user(settings, body.mfa_token)
    await service.verify_totp(sessions(request), user_id, body.code)
    issued = await service.issue_session(
        sessions(request),
        settings,
        user_id=user_id,
        tenant_id=body.tenant_id,
        user_agent=request.headers.get("user-agent"),
    )
    result = _out(issued)
    if body.remember_device:
        fingerprint = await service.device_fingerprint(sessions(request), user_id)
        if fingerprint is not None:
            result.device_token = tokens.issue_device_token(settings, user_id, fingerprint)
    return result


@router.post("/refresh", summary="Token erneuern (Rotation)")
async def refresh(body: RefreshRequest, request: Request) -> TokenResponse:
    settings = _settings(request)
    issued = await service.rotate_refresh(
        sessions(request), settings, body.refresh_token, request.headers.get("user-agent")
    )
    return _out(issued)


@router.post("/switch-tenant", summary="Mandant wechseln")
async def switch_tenant(
    body: SwitchRequest, request: Request, principal: Principal = Depends(get_principal)
) -> TokenResponse:
    settings = _settings(request)
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="API keys cannot switch tenants."
        )
    async with platform_transaction(sessions(request)) as session:
        tenants = await service.memberships(session, principal.user_id)
    if body.tenant_id in {t.id for t in tenants}:
        issued = await service.issue_session(
            sessions(request),
            settings,
            user_id=principal.user_id,
            tenant_id=body.tenant_id,
            user_agent=request.headers.get("user-agent"),
        )
        return _out(issued)
    if not principal.is_platform_admin:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No membership in tenant.")
    reason = (body.reason or "").strip()
    if len(reason) < 10:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Für den Plattformzugriff ist eine Begründung "
                "mit mindestens 10 Zeichen erforderlich."
            ),
        )
    issued = await service.platform_switch(
        sessions(request),
        settings,
        admin_id=principal.user_id,
        tenant_id=body.tenant_id,
        reason=reason,
    )
    return _out(issued)


@router.post("/logout", status_code=204, summary="Sitzung beenden")
async def logout(body: RefreshRequest, request: Request) -> Response:
    owner = await service.family_of(sessions(request), body.refresh_token)
    if owner is not None:
        await service.revoke_family(sessions(request), owner[0], owner[1])
    return Response(status_code=204)


@router.post("/password", status_code=204, summary="Eigenes Passwort ändern")
async def change_password(
    body: PasswordChange, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    """Requires the current password; other sessions of the user end (only the current token
    family stays valid until it expires)."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    violation = passwords.policy_violation(body.new_password)
    if violation:
        raise ProblemError(ErrorCodes.PASSWORD_POLICY, detail=violation)
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, principal.user_id)
        if user is None or not passwords.verify_password(user.password_hash, body.current_password):
            raise ProblemError(
                ErrorCodes.INVALID_CREDENTIALS, detail="Aktuelles Passwort ist falsch."
            )
        user.password_hash = passwords.hash_password(body.new_password)
    return Response(status_code=204)


@router.get("/sessions", summary="Aktive Sitzungen (Geräteliste)")
async def list_sessions(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[SessionOut]:
    if principal.user_id is None:
        return []
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        rows = await session.execute(
            select(
                RefreshToken.family_id,
                func.min(RefreshToken.issued_at).label("started_at"),
                func.max(RefreshToken.issued_at).label("last_used_at"),
            )
            .where(
                RefreshToken.user_id == principal.user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.used_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .group_by(RefreshToken.family_id)
        )
        families = rows.all()
        result = []
        for row in families:
            latest = await session.scalar(
                select(RefreshToken)
                .where(RefreshToken.family_id == row.family_id)
                .order_by(RefreshToken.issued_at.desc())
                .limit(1)
            )
            if latest is None:  # pragma: no cover - family rows exist by construction
                continue
            result.append(
                SessionOut(
                    family_id=row.family_id,
                    tenant_id=latest.tenant_id,
                    user_agent=latest.user_agent,
                    started_at=row.started_at,
                    last_used_at=row.last_used_at,
                )
            )
    return result


@router.delete("/sessions/{family_id}", status_code=204, summary="Sitzung widerrufen")
async def revoke_session(
    family_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    if principal.user_id is None or not await service.revoke_family(
        sessions(request), principal.user_id, family_id
    ):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return Response(status_code=204)


@router.get("/me", summary="Aktueller Benutzer und Berechtigungen")
async def me(request: Request, principal: Principal = Depends(get_principal)) -> MeOut:
    email = name = None
    if principal.user_id is not None:
        async with platform_transaction(sessions(request)) as session:
            user = await session.get(User, principal.user_id)
            if user is not None:
                email, name = user.email, user.display_name
    return MeOut(
        user_id=principal.user_id,
        email=email,
        display_name=name,
        tenant_id=principal.tenant_id,
        roles=list(principal.roles),
        permissions=sorted(principal.permissions),
        is_platform_admin=principal.is_platform_admin,
        platform_access_reason=principal.platform_access_reason,
    )
