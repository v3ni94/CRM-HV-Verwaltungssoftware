"""OIDC provider for single sign-on of existing tools (section 3.4).

Authorization code flow with mandatory PKCE (S256). The authorize endpoint requires an
authenticated user (bearer); the browser login page follows with the CRM UI (M9).
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from mhvp.core.auth import service, tokens
from mhvp.core.auth.principal import Principal, get_principal, sessions
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import OidcAuthorizationCode, OidcClient, User

CODE_TTL = timedelta(seconds=60)
SUPPORTED_SCOPES = ("openid", "profile", "email")

well_known = APIRouter(tags=["Anmeldung"])
router = APIRouter(prefix="/oidc", tags=["Anmeldung"])


class OidcTokenResponse(BaseModel):
    access_token: str
    id_token: str
    token_type: str = "Bearer"
    expires_in: int


def _invalid(message: str) -> ProblemError:
    return ProblemError(ErrorCodes.OIDC_INVALID, developer_message=message)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@well_known.get("/.well-known/openid-configuration", summary="OIDC Discovery")
async def discovery(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    base = settings.jwt_issuer.rstrip("/")
    return {
        "issuer": settings.jwt_issuer,
        "authorization_endpoint": f"{base}/api/v1/oidc/authorize",
        "token_endpoint": f"{base}/api/v1/oidc/token",
        "userinfo_endpoint": f"{base}/api/v1/oidc/userinfo",
        "jwks_uri": f"{base}/api/v1/oidc/jwks",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [tokens.ALGORITHM],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
    }


@router.get("/jwks", summary="Öffentliche Signaturschlüssel")
async def jwks(request: Request) -> dict[str, list[dict[str, str]]]:
    settings: Settings = request.app.state.settings
    service.ensure_configured(settings)
    return {"keys": [tokens.public_jwk(settings)]}


@router.get("/authorize", summary="Autorisierungsanfrage (Code mit PKCE)", status_code=302)
async def authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str | None = None,
    nonce: str | None = None,
    principal: Principal = Depends(get_principal),
) -> RedirectResponse:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="User login required.")
    if response_type != "code":
        raise _invalid("unsupported response_type")
    if code_challenge_method != "S256" or not 43 <= len(code_challenge) <= 128:
        raise _invalid("PKCE with S256 is required")
    scopes = scope.split()
    if "openid" not in scopes or not set(scopes) <= set(SUPPORTED_SCOPES):
        raise _invalid("invalid scope")
    code = secrets.token_urlsafe(32)
    async with platform_transaction(sessions(request)) as session:
        client = await session.scalar(select(OidcClient).where(OidcClient.client_id == client_id))
        if client is None or not client.active or redirect_uri not in client.redirect_uris:
            raise _invalid("unknown client or redirect_uri")
        session.add(
            OidcAuthorizationCode(
                code_hash=tokens.sha256_hex(code),
                client_id=client_id,
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                redirect_uri=redirect_uri,
                scope=" ".join(scopes),
                nonce=nonce,
                code_challenge=code_challenge,
                expires_at=datetime.now(UTC) + CODE_TTL,
            )
        )
    query = {"code": code} | ({"state": state} if state else {})
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)


@router.post("/token", summary="Code gegen Token tauschen")
async def token(
    request: Request,
    grant_type: str = Form(),
    code: str = Form(),
    redirect_uri: str = Form(),
    client_id: str = Form(),
    code_verifier: str = Form(),
    client_secret: str | None = Form(default=None),
) -> OidcTokenResponse:
    settings: Settings = request.app.state.settings
    service.ensure_configured(settings)
    if grant_type != "authorization_code":
        raise _invalid("unsupported grant_type")
    now = datetime.now(UTC)
    async with platform_transaction(sessions(request)) as session:
        client = await session.scalar(select(OidcClient).where(OidcClient.client_id == client_id))
        if client is None or not client.active:
            raise _invalid("unknown client")
        if client.client_secret_hash is not None and not (
            client_secret
            and tokens.constant_time_equals(
                client.client_secret_hash, tokens.sha256_hex(client_secret)
            )
        ):
            raise _invalid("client authentication failed")
        grant = await session.scalar(
            select(OidcAuthorizationCode)
            .where(OidcAuthorizationCode.code_hash == tokens.sha256_hex(code))
            .with_for_update()
        )
        if (
            grant is None
            or grant.used_at is not None
            or grant.expires_at <= now
            or grant.client_id != client_id
            or grant.redirect_uri != redirect_uri
            or not tokens.constant_time_equals(grant.code_challenge, pkce_challenge(code_verifier))
        ):
            raise _invalid("invalid or used code")
        grant.used_at = now
        user = await session.get(User, grant.user_id)
        if user is None or not user.active:
            raise _invalid("user inactive")
        email, name, user_id, tenant_id, nonce = (
            user.email,
            user.display_name,
            user.id,
            grant.tenant_id,
            grant.nonce,
        )
    access = tokens.issue_access_token(
        settings, tokens.AccessClaims(user_id=user_id, tenant_id=tenant_id)
    )
    id_token = tokens.issue_id_token(
        settings,
        user_id=user_id,
        client_id=client_id,
        email=email,
        name=name,
        nonce=nonce,
        tenant_id=tenant_id,
    )
    return OidcTokenResponse(
        access_token=access, id_token=id_token, expires_in=settings.access_token_ttl_seconds
    )


@router.get("/userinfo", summary="Benutzerinformationen (OIDC)")
async def userinfo(
    request: Request, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, principal.user_id)
    if user is None:
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)
    return {
        "sub": str(user.id),
        "email": user.email,
        "name": user.display_name,
        "tenant_id": str(principal.tenant_id) if principal.tenant_id else None,
    }
