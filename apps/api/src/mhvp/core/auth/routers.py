"""Auth endpoints (/api/v1/auth)."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update

from mhvp.core.auth import audit, mfa_policy, passwords, service, tokens, webauthn
from mhvp.core.auth.permissions import SYSTEM_ROLES
from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    get_principal,
    require_permission,
    sessions,
    tenant_tx,
)
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.request_identity import settings_client_ip
from mhvp.platform.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    RefreshToken,
    Role,
    User,
    WebAuthnCredential,
)

router = APIRouter(prefix="/auth", tags=["Anmeldung"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    tenant_id: uuid.UUID | None = None
    # Trusted device cookie of the web BFF ("Dieses Gerät 90 Tage merken", operator
    # 26.09.2026): skips TOTP for this user while it is valid.
    device_token: str | None = Field(default=None, max_length=200)


class LoginStep(BaseModel):
    status: str = Field(description="ok, mfa_required oder mfa_setup_required")
    mfa_token: str | None = None
    # Present only when status == "ok" (password alone was enough, or a trusted device stood
    # in for TOTP): the session is already issued, exactly like TokenResponse below.
    access_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    tenant_id: uuid.UUID | None = None
    tenants: list["TenantOut"] = Field(default_factory=list)
    # Second factors the user can answer with when status == "mfa_required" (S16-01).
    mfa_methods: list[str] = Field(default_factory=list)
    # M2-04: status == "mfa_setup_required" (the tenant policy demands a second factor, the
    # user has none yet): token for /auth/mfa/setup/start and /auth/mfa/setup/confirm only.
    mfa_setup_token: str | None = None


class MfaSetup(BaseModel):
    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)
    tenant_id: uuid.UUID | None = None
    # "Dieses Gerät 90 Tage merken" (operator 26.09.2026, M2-01).
    remember_device: bool = False


class TotpConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)


class AuthMfaSetupStartRequest(BaseModel):
    """M2-04: enrolment inside the login flow, authorised by the setup token only."""

    mfa_setup_token: str = Field(min_length=10, max_length=4096)


class AuthMfaSetupConfirmRequest(BaseModel):
    mfa_setup_token: str = Field(min_length=10, max_length=4096)
    code: str = Field(min_length=6, max_length=8)
    tenant_id: uuid.UUID | None = None
    remember_device: bool = False


class AuthMfaPolicyOut(BaseModel):
    """Second factor policy of the tenant (M2-04, docs/rules/M2-04.md). Without a stored row the
    default applies: ``voluntary`` (operator decision M2-01), portal not required."""

    crm_mode: str
    crm_role_codes: list[str]
    portal_required: bool
    # False while the tenant runs on the default (no stored row, ``voluntary``).
    stored: bool
    # Role codes of the tenant (system and custom) for the role list, portal role excluded.
    available_role_codes: list[str]


class AuthMfaPolicyUpdate(BaseModel):
    """Replaces the policy. ``voluntary`` is the default without a policy (M2-01); ``all_staff``
    and ``roles`` are tenant choices that make the second factor mandatory."""

    model_config = {"extra": "forbid"}

    crm_mode: Literal["all_staff", "roles", "voluntary"]
    crm_role_codes: list[str] = Field(default_factory=list, max_length=100)
    portal_required: bool


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
    # Raw device token, returned once, only when the caller asked to remember this device.
    device_token: str | None = None


class TrustedDeviceOut(BaseModel):
    id: uuid.UUID
    label: str | None
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None


class AuthWebAuthnStatus(BaseModel):
    """M2-03: Passkeys (WebAuthn) als optionaler zweiter Faktor."""

    available: bool
    reason: str | None = None
    credential_count: int = 0


class AuthWebAuthnCredentialOut(BaseModel):
    id: uuid.UUID
    label: str | None
    created_at: datetime
    last_used_at: datetime | None
    passwordless: bool = False


class AuthWebAuthnRegisterOptionsRequest(BaseModel):
    passwordless: bool = False


class AuthWebAuthnOptionsOut(BaseModel):
    """``challenge_id`` goes back with the verify call; ``public_key`` is handed to
    ``navigator.credentials.create/get`` (binary fields base64url encoded)."""

    challenge_id: str
    public_key: dict[str, Any]


class AuthWebAuthnAttestationResponse(BaseModel):
    client_data_json: str = Field(min_length=1, max_length=4096)
    attestation_object: str = Field(min_length=1, max_length=16384)
    transports: list[str] = Field(default_factory=list, max_length=8)


class AuthWebAuthnRegisterVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=10, max_length=100)
    credential_id: str = Field(min_length=1, max_length=1400)
    response: AuthWebAuthnAttestationResponse
    label: str | None = Field(default=None, max_length=200)


class AuthWebAuthnLoginOptionsRequest(BaseModel):
    # With mfa_token: second factor after the password. Without: passwordless sign in.
    mfa_token: str | None = Field(default=None, max_length=4096)


class AuthWebAuthnAssertionResponse(BaseModel):
    client_data_json: str = Field(min_length=1, max_length=4096)
    authenticator_data: str = Field(min_length=1, max_length=4096)
    signature: str = Field(min_length=1, max_length=2048)
    user_handle: str | None = Field(default=None, max_length=200)


class AuthWebAuthnLoginVerifyRequest(BaseModel):
    challenge_id: str = Field(min_length=10, max_length=100)
    credential_id: str = Field(min_length=1, max_length=1400)
    response: AuthWebAuthnAssertionResponse
    mfa_token: str | None = Field(default=None, max_length=4096)
    tenant_id: uuid.UUID | None = None
    remember_device: bool = False


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
    # The single superadmin (ADR 0011): only true together with is_platform_admin.
    is_superadmin: bool = False
    platform_access_reason: str | None
    # Second factor switched on by the user (Einstellungen, Sicherheit).
    totp_enabled: bool = False
    # M2-04: the tenant policy demands a second factor for this user (TOTP cannot be switched
    # off then; without a factor the next login asks for the setup).
    mfa_required: bool = False
    # UI preferences (operator 27.09.2026, migration 0182), served with getMe so the main
    # navigation renders its stored state without a flash of the wrong layout.
    ui_preferences: dict[str, Any] = Field(default_factory=dict)
    # AF19-R: the tenant carries the demo flag (migration 0392); drives the demo banner.
    is_demo: bool = False


# Accepted keys of ``User.ui_preferences`` (rule: only these are ever written, unknown keys are
# rejected so the bag stays a small, reviewable set rather than an arbitrary blob).
_UI_PREFERENCE_KEYS = {"nav_expanded_groups", "theme"}


class UiPreferencesUpdate(BaseModel):
    """Partial update: only listed keys are merged into ``User.ui_preferences``. Unknown keys
    are rejected (``extra="forbid"``) so the bag stays a small, reviewable set."""

    model_config = {"extra": "forbid"}

    nav_expanded_groups: list[str] | None = None
    # Appearance of the web CRM (operator 27.09.2026): day (design A), evening (design B) or
    # auto (evening from 19 to 7 o'clock local time, evaluated in the browser).
    theme: Literal["day", "evening", "auto"] | None = None

    def as_patch(self) -> dict[str, Any]:
        data = self.model_dump(exclude_unset=True)
        unknown = set(data) - _UI_PREFERENCE_KEYS
        if unknown:
            raise ProblemError(ErrorCodes.VALIDATION)
        return data


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    service.ensure_configured(settings)
    return settings


def _out(issued: service.IssuedTokens, *, device_token: str | None = None) -> TokenResponse:
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token,
        tenant_id=issued.tenant_id,
        tenants=[TenantOut(id=t.id, name=t.name) for t in issued.tenants],
        device_token=device_token,
    )


async def _audit(
    request: Request,
    user_id: uuid.UUID,
    type: str,
    *,
    tenant_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """GAH-302: security event of the login flow (no passwords, codes or tokens)."""
    await audit.record(
        sessions(request), user_id=user_id, type=type, tenant_id=tenant_id, payload=payload
    )


def _ok_step(issued: service.IssuedTokens) -> LoginStep:
    out = _out(issued)
    return LoginStep(
        status="ok",
        access_token=out.access_token,
        expires_in=out.expires_in,
        refresh_token=out.refresh_token,
        tenant_id=out.tenant_id,
        tenants=out.tenants,
    )


def _mfa_user(settings: Settings, token: str) -> uuid.UUID:
    try:
        return tokens.decode_mfa_token(settings, token)
    except (tokens.TokenError, ValueError, KeyError):
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED) from None


@router.post("/login", summary="Anmeldung Schritt 1: E-Mail und Passwort")
async def login(body: LoginRequest, request: Request) -> LoginStep:
    """The session is issued right here unless the user has a second factor (enabled under
    Einstellungen, Sicherheit) or the tenant's second factor policy covers the user (M2-04;
    the default is voluntary, so only a tenant that chose the obligation). A trusted device
    ("Dieses Gerät 90 Tage merken") stands in for the second factor. A user under the policy
    without any factor gets ``mfa_setup_required`` and sets up TOTP in the login flow
    (transition, no lockout)."""
    settings = _settings(request)
    user_id, totp_enabled = await service.check_password(
        sessions(request), body.email, body.password
    )
    methods = await _second_factor_methods(request, settings, user_id, totp_enabled)
    second_factor = bool(methods)
    if not second_factor and await mfa_policy.user_requires_second_factor(
        sessions(request), user_id
    ):
        return LoginStep(
            status="mfa_setup_required",
            mfa_setup_token=tokens.issue_mfa_setup_token(
                settings, user_id, tenant_id=body.tenant_id
            ),
        )
    trusted = (
        second_factor
        and body.device_token is not None
        and await service.check_trusted_device(
            sessions(request), user_id=user_id, raw_token=body.device_token
        )
    )
    if not second_factor or trusted:
        issued = await service.issue_session(
            sessions(request),
            settings,
            user_id=user_id,
            tenant_id=body.tenant_id,
            user_agent=request.headers.get("user-agent"),
        )
        # Password only and trusted device logins skip verify_totp, which otherwise records
        # the login (last_login_at feeds the portal account list, A86).
        await service.record_login(sessions(request), user_id)
        await _audit(
            request,
            user_id,
            audit.LOGIN_SUCCEEDED,
            payload={"method": "trusted_device" if trusted else "password"},
        )
        return _ok_step(issued)
    return LoginStep(
        status="mfa_required",
        mfa_token=tokens.issue_mfa_token(settings, user_id),
        mfa_methods=methods,
    )


async def _second_factor_methods(
    request: Request, settings: Settings, user_id: uuid.UUID, totp_enabled: bool
) -> list[str]:
    methods = ["totp"] if totp_enabled else []
    if webauthn.is_available(settings) and await _has_passkey(request, user_id):
        methods.append("webauthn")
    return methods


def _setup_user(settings: Settings, token: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    try:
        return tokens.decode_mfa_setup_token(settings, token)
    except (tokens.TokenError, ValueError, KeyError):
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED) from None


async def _refuse_setup_with_factor(
    request: Request, settings: Settings, user_id: uuid.UUID
) -> None:
    """The setup step exists only for users without any second factor: a user who has one
    (TOTP or a usable passkey) must answer with it, never enrol a new one with the password."""
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, user_id)
        if user is None or not user.active:
            raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)
        totp_enabled = user.totp_enabled
    if await _second_factor_methods(request, settings, user_id, totp_enabled):
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)


@router.post(
    "/mfa/setup/start",
    summary="Anmeldung: zweiten Faktor einrichten, Schlüssel erzeugen (M2-04)",
)
async def mfa_setup_start(body: AuthMfaSetupStartRequest, request: Request) -> MfaSetup:
    """Only with the setup token from ``/auth/login`` (status ``mfa_setup_required``). Creates
    a pending TOTP secret; it becomes effective with ``/auth/mfa/setup/confirm``."""
    settings = _settings(request)
    user_id, _tenant = _setup_user(settings, body.mfa_setup_token)
    await _refuse_setup_with_factor(request, settings, user_id)
    secret, uri = await service.start_totp_setup(sessions(request), user_id)
    return MfaSetup(secret=secret, otpauth_uri=uri)


@router.post(
    "/mfa/setup/confirm",
    summary="Anmeldung: zweiten Faktor bestätigen und Sitzung ausstellen (M2-04)",
)
async def mfa_setup_confirm(body: AuthMfaSetupConfirmRequest, request: Request) -> TokenResponse:
    """Confirms the pending secret with a matching code (wrong codes count towards the
    lockout), switches TOTP on and issues the session, like ``/auth/mfa/verify``."""
    settings = _settings(request)
    user_id, token_tenant = _setup_user(settings, body.mfa_setup_token)
    await _refuse_setup_with_factor(request, settings, user_id)
    await service.enable_totp(sessions(request), user_id, body.code)
    tenant_id = body.tenant_id or token_tenant
    issued = await service.issue_session(
        sessions(request),
        settings,
        user_id=user_id,
        tenant_id=tenant_id,
        user_agent=request.headers.get("user-agent"),
    )
    await service.record_login(sessions(request), user_id)
    device_token = None
    if body.remember_device:
        device_token = tokens.new_opaque_secret()
        await service.store_trusted_device(
            sessions(request),
            user_id=user_id,
            tenant_id=tenant_id,
            raw_token=device_token,
            user_agent=request.headers.get("user-agent"),
        )
    await _audit(request, user_id, audit.TOTP_ENABLED)
    await _audit(
        request,
        user_id,
        audit.LOGIN_SUCCEEDED,
        payload={"method": "totp_setup"},
    )
    return _out(issued, device_token=device_token)


@router.post("/totp/setup", summary="Zweiten Faktor (TOTP) einrichten: Schlüssel erzeugen")
async def totp_setup(request: Request, principal: Principal = Depends(get_principal)) -> MfaSetup:
    """Einstellungen, Sicherheit: creates a pending secret for the signed in user. It becomes
    effective only after ``/totp/confirm`` with a matching code."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    secret, uri = await service.start_totp_setup(sessions(request), principal.user_id)
    return MfaSetup(secret=secret, otpauth_uri=uri)


@router.post("/totp/confirm", status_code=204, summary="Zweiten Faktor (TOTP) bestätigen")
async def totp_confirm(
    body: TotpConfirmRequest, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    await service.enable_totp(sessions(request), principal.user_id, body.code)
    await _audit(request, principal.user_id, audit.TOTP_ENABLED)
    return Response(status_code=204)


@router.post("/totp/disable", status_code=204, summary="Zweiten Faktor (TOTP) abschalten")
async def totp_disable(
    body: TotpDisableRequest, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    """Requires the current password; every remembered device is revoked as well. Refused
    while the tenant policy covers the user and TOTP is the only second factor (M2-04)."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    settings = request.app.state.settings
    if not (
        webauthn.is_available(settings) and await _has_passkey(request, principal.user_id)
    ) and await mfa_policy.user_requires_second_factor(sessions(request), principal.user_id):
        raise ProblemError(ErrorCodes.MFA_REQUIRED_BY_POLICY)
    await service.disable_totp(sessions(request), principal.user_id, body.current_password)
    await _audit(request, principal.user_id, audit.TOTP_DISABLED)
    return Response(status_code=204)


@router.post("/mfa/verify", summary="Anmeldung Schritt 2: TOTP-Code, Token ausstellen")
async def mfa_verify(body: MfaVerifyRequest, request: Request) -> TokenResponse:
    settings = _settings(request)
    user_id = _mfa_user(settings, body.mfa_token)
    await service.verify_totp(sessions(request), user_id, body.code)
    # M2-04: a magic link login handing over to TOTP names its tenant in the step token.
    tenant_id = body.tenant_id or tokens.mfa_token_tenant(settings, body.mfa_token)
    issued = await service.issue_session(
        sessions(request),
        settings,
        user_id=user_id,
        tenant_id=tenant_id,
        user_agent=request.headers.get("user-agent"),
    )
    device_token = None
    if body.remember_device:
        device_token = tokens.new_opaque_secret()
        await service.store_trusted_device(
            sessions(request),
            user_id=user_id,
            tenant_id=tenant_id,
            raw_token=device_token,
            user_agent=request.headers.get("user-agent"),
        )
    await _audit(
        request,
        user_id,
        audit.LOGIN_SUCCEEDED,
        payload={"method": "totp", "remember_device": bool(body.remember_device)},
    )
    return _out(issued, device_token=device_token)


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
    """Requires the current password. All refresh tokens of the user are revoked, so every
    session (also on other devices) ends once its access token expires and needs the new
    password (SECURITY-2026-10-01, Befund 5: before, no session ended)."""
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
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    await _audit(request, principal.user_id, audit.PASSWORD_CHANGED)
    return Response(status_code=204)


@router.get(
    "/sessions", summary="Aktive Sitzungen (Geräteliste)", dependencies=[Depends(strict_query)]
)
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
    await _audit(
        request, principal.user_id, audit.SESSION_REVOKED, payload={"family_id": str(family_id)}
    )
    return Response(status_code=204)


@router.get(
    "/trusted-devices",
    summary="Gemerkte Geräte (TOTP-Ausnahme)",
    dependencies=[Depends(strict_query)],
)
async def list_trusted_devices(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[TrustedDeviceOut]:
    if principal.user_id is None:
        return []
    devices = await service.list_trusted_devices(sessions(request), principal.user_id)
    return [
        TrustedDeviceOut(
            id=d.id,
            label=d.label,
            created_at=d.created_at,
            expires_at=d.expires_at,
            last_used_at=d.last_used_at,
        )
        for d in devices
    ]


@router.delete(
    "/trusted-devices/{device_id}", status_code=204, summary="Gemerktes Gerät widerrufen"
)
async def revoke_trusted_device(
    device_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    if principal.user_id is None or not await service.revoke_trusted_device(
        sessions(request), principal.user_id, device_id
    ):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await _audit(
        request,
        principal.user_id,
        audit.TRUSTED_DEVICE_REVOKED,
        payload={"device_id": str(device_id)},
    )
    return Response(status_code=204)


def _webauthn_active(user_id: uuid.UUID) -> Any:
    return select(WebAuthnCredential).where(
        WebAuthnCredential.user_id == user_id, WebAuthnCredential.revoked_at.is_(None)
    )


@router.get("/webauthn/status", summary="Passkeys (WebAuthn): Verfügbarkeit (M2-03)")
async def webauthn_status(
    request: Request, principal: Principal = Depends(get_principal)
) -> AuthWebAuthnStatus:
    count = 0
    if principal.user_id is not None:
        async with platform_transaction(sessions(request)) as session:
            count = len((await session.scalars(_webauthn_active(principal.user_id))).all())
    available = webauthn.is_available(request.app.state.settings)
    return AuthWebAuthnStatus(
        available=available,
        reason=None if available else webauthn.UNAVAILABLE_REASON,
        credential_count=count,
    )


@router.get(
    "/webauthn/credentials",
    summary="Eigene Passkeys (WebAuthn) auflisten",
    dependencies=[Depends(strict_query)],
)
async def list_webauthn_credentials(
    request: Request, principal: Principal = Depends(get_principal)
) -> list[AuthWebAuthnCredentialOut]:
    if principal.user_id is None:
        return []
    async with platform_transaction(sessions(request)) as session:
        rows = (
            await session.scalars(
                _webauthn_active(principal.user_id).order_by(WebAuthnCredential.created_at)
            )
        ).all()
        return [
            AuthWebAuthnCredentialOut(
                id=r.id,
                label=r.label,
                created_at=r.created_at,
                last_used_at=r.last_used_at,
                passwordless=r.passwordless,
            )
            for r in rows
        ]


@router.delete(
    "/webauthn/credentials/{credential_id}", status_code=204, summary="Eigenen Passkey widerrufen"
)
async def revoke_webauthn_credential(
    credential_id: uuid.UUID, request: Request, principal: Principal = Depends(get_principal)
) -> Response:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    async with platform_transaction(sessions(request)) as session:
        row = await session.scalar(
            _webauthn_active(principal.user_id).where(WebAuthnCredential.id == credential_id)
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        user = await session.get(User, principal.user_id)
        others = len((await session.scalars(_webauthn_active(principal.user_id))).all()) - 1
        last_factor = not (user is not None and user.totp_enabled) and others <= 0
    # M2-04: the last second factor of a user under the tenant policy stays.
    if last_factor and await mfa_policy.user_requires_second_factor(
        sessions(request), principal.user_id
    ):
        raise ProblemError(ErrorCodes.MFA_REQUIRED_BY_POLICY)
    async with platform_transaction(sessions(request)) as session:
        await session.execute(
            update(WebAuthnCredential)
            .where(
                WebAuthnCredential.id == credential_id,
                WebAuthnCredential.user_id == principal.user_id,
                WebAuthnCredential.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    await _audit(
        request,
        principal.user_id,
        audit.PASSKEY_REVOKED,
        payload={"credential_id": str(credential_id)},
    )
    return Response(status_code=204)


async def _has_passkey(request: Request, user_id: uuid.UUID) -> bool:
    async with platform_transaction(sessions(request)) as session:
        return (await session.scalar(_webauthn_active(user_id).limit(1))) is not None


def _redis(request: Request) -> Any:
    return request.app.state.resources.redis


async def _is_portal_only_user(request: Request, user_id: uuid.UUID) -> bool:
    """U04-02: marker of a pure portal account. True when the user has active memberships and
    every one of them carries only the role ``portal_user`` (portal accounts are created
    with exactly that role, CRM staff hold other roles). No membership: not portal only."""
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        memberships = (
            await session.execute(
                select(Membership.id, Membership.tenant_id).where(
                    Membership.user_id == user_id, Membership.status == MembershipStatus.ACTIVE
                )
            )
        ).all()
    if not memberships:
        return False
    for membership_id, tenant_id in memberships:
        async with tenant_transaction(factory, tenant_id) as session:
            codes = set(
                await session.scalars(
                    select(Role.code)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(MembershipRole.membership_id == membership_id)
                )
            )
        if codes != {"portal_user"}:
            return False
    return True


async def _refuse_passwordless_for_portal(request: Request, user_id: uuid.UUID) -> None:
    if await _is_portal_only_user(request, user_id):
        raise ProblemError(ErrorCodes.WEBAUTHN_PASSWORDLESS_FORBIDDEN)


@router.post(
    "/webauthn/register/options",
    summary="Passkey registrieren: Optionen (S16-01)",
    responses={503: {"description": "MHVP-AUTH-0012"}},
)
async def webauthn_register_options(
    request: Request,
    body: AuthWebAuthnRegisterOptionsRequest | None = None,
    principal: Principal = Depends(get_principal),
) -> AuthWebAuthnOptionsOut:
    """Creation options for the signed in user (attestation none). ``passwordless`` asks for a
    discoverable credential with user verification."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    settings = request.app.state.settings
    webauthn.ensure_available(settings)
    await webauthn.enforce_options_limit(
        _redis(request),
        settings,
        scope="register",
        ip=settings_client_ip(request.scope, settings),
        user_id=str(principal.user_id),
    )
    passwordless = bool(body and body.passwordless)
    if passwordless:
        await _refuse_passwordless_for_portal(request, principal.user_id)
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, principal.user_id)
        if user is None or not user.active:
            raise ProblemError(ErrorCodes.FORBIDDEN)
        existing = (await session.scalars(_webauthn_active(user.id))).all()
        email, display = user.email, user.display_name or user.email
    challenge_id, challenge = await webauthn.issue_challenge(
        _redis(request),
        purpose="register",
        user_id=str(principal.user_id),
        passwordless=passwordless,
    )
    options = {
        "rp": {"id": settings.webauthn_rp_id, "name": settings.webauthn_rp_name},
        "user": {
            "id": webauthn.b64url_encode(principal.user_id.bytes),
            "name": email,
            "displayName": display,
        },
        "challenge": webauthn.b64url_encode(challenge),
        "pubKeyCredParams": [
            {"type": "public-key", "alg": alg} for alg in webauthn.SUPPORTED_ALGORITHMS
        ],
        "timeout": webauthn.TIMEOUT_MS,
        "attestation": "none",
        "excludeCredentials": [
            {"type": "public-key", "id": c.credential_id, "transports": c.transports}
            for c in existing
        ],
        "authenticatorSelection": {
            "residentKey": "required" if passwordless else "discouraged",
            "requireResidentKey": passwordless,
            "userVerification": "required" if passwordless else "preferred",
        },
    }
    return AuthWebAuthnOptionsOut(challenge_id=challenge_id, public_key=options)


@router.post(
    "/webauthn/register/verify",
    status_code=201,
    summary="Passkey registrieren: Antwort prüfen (S16-01)",
    responses={503: {"description": "MHVP-AUTH-0012"}, 401: {"description": "MHVP-AUTH-0013"}},
)
async def webauthn_register_verify(
    body: AuthWebAuthnRegisterVerifyRequest,
    request: Request,
    principal: Principal = Depends(get_principal),
) -> AuthWebAuthnCredentialOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    settings = request.app.state.settings
    webauthn.ensure_available(settings)
    challenge = await webauthn.consume_challenge(
        _redis(request), body.challenge_id, purpose="register"
    )
    if challenge.get("user_id") != str(principal.user_id):
        raise webauthn.invalid("Challenge issued to another user.")
    passwordless = bool(challenge.get("passwordless"))
    if passwordless:
        await _refuse_passwordless_for_portal(request, principal.user_id)
    registered = webauthn.verify_registration(
        settings,
        challenge=challenge["challenge_bytes"],
        credential_id=body.credential_id,
        client_data_json=body.response.client_data_json,
        attestation_object=body.response.attestation_object,
        require_user_verification=passwordless,
    )
    async with platform_transaction(sessions(request)) as session:
        taken = await session.scalar(
            select(WebAuthnCredential.id).where(
                WebAuthnCredential.credential_id == registered.credential_id
            )
        )
        if taken is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Dieser Passkey ist bereits registriert."
            )
        row = WebAuthnCredential(
            user_id=principal.user_id,
            credential_id=registered.credential_id,
            public_key=registered.public_key,
            sign_count=registered.sign_count,
            transports=[t[:20] for t in body.response.transports],
            aaguid=registered.aaguid,
            label=(body.label or "").strip() or None,
            passwordless=passwordless,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        out = AuthWebAuthnCredentialOut(
            id=row.id,
            label=row.label,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            passwordless=row.passwordless,
        )
    await _audit(
        request,
        principal.user_id,
        audit.PASSKEY_REGISTERED,
        payload={"credential_id": str(out.id), "passwordless": out.passwordless},
    )
    return out


@router.post(
    "/login/webauthn/options",
    summary="Anmeldung mit Passkey: Optionen (zweiter Faktor oder ohne Passwort, S16-01)",
    responses={503: {"description": "MHVP-AUTH-0012"}},
)
async def webauthn_login_options(
    body: AuthWebAuthnLoginOptionsRequest, request: Request
) -> AuthWebAuthnOptionsOut:
    settings = _settings(request)
    webauthn.ensure_available(settings)
    allow: list[dict[str, Any]] = []
    user_id: uuid.UUID | None = None
    if body.mfa_token is not None:
        user_id = _mfa_user(settings, body.mfa_token)
    await webauthn.enforce_options_limit(
        _redis(request),
        settings,
        scope="login",
        ip=settings_client_ip(request.scope, settings),
        user_id=str(user_id) if user_id else None,
    )
    if user_id is not None:
        async with platform_transaction(sessions(request)) as session:
            rows = (await session.scalars(_webauthn_active(user_id))).all()
        allow = [
            {"type": "public-key", "id": r.credential_id, "transports": r.transports} for r in rows
        ]
        if not allow:
            raise webauthn.invalid("No passkey registered for this user.")
    challenge_id, challenge = await webauthn.issue_challenge(
        _redis(request),
        purpose="login",
        user_id=str(user_id) if user_id else None,
    )
    options = {
        "challenge": webauthn.b64url_encode(challenge),
        "rpId": settings.webauthn_rp_id,
        "timeout": webauthn.TIMEOUT_MS,
        "allowCredentials": allow,
        "userVerification": "preferred" if user_id else "required",
    }
    return AuthWebAuthnOptionsOut(challenge_id=challenge_id, public_key=options)


@router.post(
    "/login/webauthn/verify",
    summary="Anmeldung mit Passkey: Antwort prüfen, Token ausstellen (S16-01)",
    responses={503: {"description": "MHVP-AUTH-0012"}, 401: {"description": "MHVP-AUTH-0013"}},
)
async def webauthn_login_verify(
    body: AuthWebAuthnLoginVerifyRequest, request: Request
) -> TokenResponse:
    """Second factor (challenge bound to the ``mfa_token`` user) or passwordless sign in
    (only credentials registered with ``passwordless``, user verification required). The
    challenge is consumed before any check; failures count towards the account lockout."""
    settings = _settings(request)
    webauthn.ensure_available(settings)
    challenge = await webauthn.consume_challenge(
        _redis(request), body.challenge_id, purpose="login"
    )
    bound_user = challenge.get("user_id")
    if bound_user is not None:
        if body.mfa_token is None or str(_mfa_user(settings, body.mfa_token)) != bound_user:
            raise webauthn.invalid("Challenge bound to another login.")
    elif body.mfa_token is not None or body.remember_device:
        raise webauthn.invalid("Passwordless challenge used as second factor.")
    now = datetime.now(UTC)
    failure: ProblemError | None = None
    async with platform_transaction(sessions(request)) as session:
        row = await session.scalar(
            select(WebAuthnCredential)
            .where(
                WebAuthnCredential.credential_id == body.credential_id.rstrip("="),
                WebAuthnCredential.revoked_at.is_(None),
            )
            .with_for_update()
        )
        if row is None or (bound_user is not None and str(row.user_id) != bound_user):
            raise webauthn.invalid("Credential unknown, revoked or of another user.")
        if bound_user is None and not row.passwordless:
            raise webauthn.invalid("Credential not released for passwordless sign in.")
        passwordless_user_id = row.user_id if bound_user is None else None
        handle = body.response.user_handle
        if handle and webauthn.b64url_decode(handle) != row.user_id.bytes:
            # WebAuthn 7.2 step 6: a returned user handle must belong to the credential owner.
            raise webauthn.invalid("User handle does not match the credential owner.")
        user = await session.get(User, row.user_id)
        if user is None or not user.active:
            # W01: same answer as an unknown credential (no account state enumeration).
            raise webauthn.invalid("Credential owner inactive.")
        if user.locked_until is not None and user.locked_until > now:
            raise ProblemError(ErrorCodes.ACCOUNT_LOCKED)
        try:
            new_count = webauthn.verify_assertion(
                settings,
                challenge=challenge["challenge_bytes"],
                public_key=row.public_key,
                stored_sign_count=row.sign_count,
                client_data_json=body.response.client_data_json,
                authenticator_data=body.response.authenticator_data,
                signature=body.response.signature,
                require_user_verification=bound_user is None,
            )
        except ProblemError as exc:
            await service.register_failed_attempt(session, user, now)
            failure = exc
        else:
            row.sign_count = new_count
            row.last_used_at = now
            user.failed_logins = 0
            user.last_login_at = now
        user_id = user.id
    if failure is not None:
        await _audit(
            request,
            user_id,
            audit.LOGIN_FAILED,
            payload={"factor": "passkey", "reason": "assertion_invalid"},
        )
        raise failure
    if passwordless_user_id is not None:
        await _refuse_passwordless_for_portal(request, passwordless_user_id)
    issued = await service.issue_session(
        sessions(request),
        settings,
        user_id=user_id,
        tenant_id=body.tenant_id,
        user_agent=request.headers.get("user-agent"),
    )
    device_token = None
    if body.remember_device:
        device_token = tokens.new_opaque_secret()
        await service.store_trusted_device(
            sessions(request),
            user_id=user_id,
            tenant_id=body.tenant_id,
            raw_token=device_token,
            user_agent=request.headers.get("user-agent"),
        )
    await _audit(
        request,
        user_id,
        audit.LOGIN_SUCCEEDED,
        payload={"method": "passkey", "passwordless": passwordless_user_id is not None},
    )
    return _out(issued, device_token=device_token)


async def _mfa_required_here(request: Request, principal: Principal) -> bool:
    """M2-04 hint for the UI: does the policy of the current tenant cover this membership?
    (The login and the switch off checks evaluate every membership of the user.)"""
    if principal.user_id is None or principal.tenant_id is None or principal.api_key_id:
        return False
    if principal.platform_access_reason:
        return False  # platform access without membership (5.1)
    async with tenant_transaction(sessions(request), principal.tenant_id) as session:
        policy = await mfa_policy.load_policy(session)
    return mfa_policy.requires_second_factor(policy, list(principal.roles))


def _policy_out(policy: mfa_policy.MfaPolicy, role_codes: list[str]) -> AuthMfaPolicyOut:
    return AuthMfaPolicyOut(
        crm_mode=policy.crm_mode,
        crm_role_codes=list(policy.crm_role_codes),
        portal_required=policy.portal_required,
        stored=policy.stored,
        available_role_codes=role_codes,
    )


async def _tenant_role_codes(session: Any) -> list[str]:
    codes = set(await session.scalars(select(Role.code)))
    codes |= {r.code for r in SYSTEM_ROLES}
    return sorted(codes - {mfa_policy.PORTAL_ROLE_CODE})


@router.get(
    "/mfa-policy",
    summary="Richtlinie zweiter Faktor des Mandanten (M2-04)",
    dependencies=[Depends(strict_query)],
)
async def get_mfa_policy(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> AuthMfaPolicyOut:
    async with tenant_tx(request, principal) as session:
        policy = await mfa_policy.load_policy(session)
        codes = await _tenant_role_codes(session)
    return _policy_out(policy, codes)


@router.put("/mfa-policy", summary="Richtlinie zweiter Faktor des Mandanten ändern (M2-04)")
async def put_mfa_policy(
    body: AuthMfaPolicyUpdate,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> AuthMfaPolicyOut:
    """Takes effect at each user's next login (running sessions stay). Mode ``roles`` needs at
    least one known role code; the portal role is governed by ``portal_required`` only."""
    async with tenant_tx(request, principal) as session:
        known = await _tenant_role_codes(session)
        codes = sorted({c.strip() for c in body.crm_role_codes if c.strip()})
        unknown = [c for c in codes if c not in known]
        if unknown:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Unbekannte Rolle: {', '.join(unknown)}.",
            )
        if body.crm_mode == "roles" and not codes:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Für die Pflicht je Rolle mindestens eine Rolle auswählen.",
            )
        policy = await mfa_policy.store_policy(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            crm_mode=body.crm_mode,
            crm_role_codes=codes if body.crm_mode == "roles" else [],
            portal_required=body.portal_required,
        )
    return _policy_out(policy, known)


async def _tenant_is_demo(request: Request, principal: Principal) -> bool:
    """Demo flag of the principal's tenant (``tenant`` has no RLS); False without a tenant."""
    if principal.tenant_id is None:
        return False
    from mhvp.platform.demo import is_demo_tenant

    async with platform_transaction(sessions(request)) as session:
        return await is_demo_tenant(session, principal.tenant_id)


@router.get("/me", summary="Aktueller Benutzer und Berechtigungen")
async def me(request: Request, principal: Principal = Depends(get_principal)) -> MeOut:
    email = name = None
    totp_enabled = False
    ui_preferences: dict[str, Any] = {}
    if principal.user_id is not None:
        async with platform_transaction(sessions(request)) as session:
            user = await session.get(User, principal.user_id)
            if user is not None:
                email, name = user.email, user.display_name
                totp_enabled = user.totp_enabled
                ui_preferences = dict(user.ui_preferences or {})
    return MeOut(
        user_id=principal.user_id,
        email=email,
        display_name=name,
        tenant_id=principal.tenant_id,
        roles=list(principal.roles),
        permissions=sorted(principal.permissions),
        is_platform_admin=principal.is_platform_admin,
        is_superadmin=principal.is_superadmin,
        platform_access_reason=principal.platform_access_reason,
        totp_enabled=totp_enabled,
        mfa_required=await _mfa_required_here(request, principal),
        ui_preferences=ui_preferences,
        is_demo=await _tenant_is_demo(request, principal),
    )


@router.patch("/me/preferences", summary="Eigene UI-Einstellungen speichern")
async def update_my_preferences(
    request: Request,
    body: UiPreferencesUpdate,
    principal: Principal = Depends(get_principal),
) -> MeOut:
    """Merge accepted keys into the caller's own ``ui_preferences`` (never another user's)."""
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    patch = body.as_patch()
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, principal.user_id)
        if user is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        merged = dict(user.ui_preferences or {})
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        user.ui_preferences = merged
        await session.flush()
        email, name, totp_enabled = user.email, user.display_name, user.totp_enabled
        ui_preferences = dict(user.ui_preferences)
    return MeOut(
        user_id=principal.user_id,
        email=email,
        display_name=name,
        tenant_id=principal.tenant_id,
        roles=list(principal.roles),
        permissions=sorted(principal.permissions),
        is_platform_admin=principal.is_platform_admin,
        is_superadmin=principal.is_superadmin,
        platform_access_reason=principal.platform_access_reason,
        totp_enabled=totp_enabled,
        mfa_required=await _mfa_required_here(request, principal),
        ui_preferences=ui_preferences,
        is_demo=await _tenant_is_demo(request, principal),
    )
