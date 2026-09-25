"""Access tokens (JWT ES256), MFA step tokens and opaque secrets."""

import base64
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mhvp.core.config import Settings

ALGORITHM = "ES256"
ACCESS_AUDIENCE = "mhvp-api"
MFA_AUDIENCE = "mhvp-mfa"
MFA_TTL = timedelta(minutes=5)
# Trusted device: skips only the TOTP step after a correct password (A-2FA-Policy).
DEVICE_AUDIENCE = "mhvp-device"
DEVICE_TTL = timedelta(days=180)


class TokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID | None
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    platform: bool = False
    platform_access_reason: str | None = None


def generate_private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _private_key(settings: Settings) -> ec.EllipticCurvePrivateKey:
    if settings.jwt_private_key is None:
        raise TokenError("MHVP_JWT_PRIVATE_KEY is not configured")
    pem = settings.jwt_private_key.get_secret_value().replace("\\n", "\n")
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise TokenError("MHVP_JWT_PRIVATE_KEY is not a valid PEM key") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TokenError("MHVP_JWT_PRIVATE_KEY must be an EC P-256 key")
    return key


def _b64(value: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(32, "big")).rstrip(b"=").decode()


def public_jwk(settings: Settings) -> dict[str, str]:
    numbers = _private_key(settings).public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "x": _b64(numbers.x), "y": _b64(numbers.y)}
    thumbprint = hashlib.sha256(
        f'{{"crv":"P-256","kty":"EC","x":"{jwk["x"]}","y":"{jwk["y"]}"}}'.encode()
    ).digest()
    jwk.update(
        kid=base64.urlsafe_b64encode(thumbprint).rstrip(b"=").decode(), use="sig", alg=ALGORITHM
    )
    return jwk


def _encode(settings: Settings, claims: dict[str, Any]) -> str:
    return jwt.encode(
        claims,
        _private_key(settings),
        algorithm=ALGORITHM,
        headers={"kid": public_jwk(settings)["kid"]},
    )


def _decode(settings: Settings, token: str, audience: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            _private_key(settings).public_key(),
            algorithms=[ALGORITHM],
            audience=audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc
    return claims


def issue_access_token(
    settings: Settings, claims: AccessClaims, *, now: datetime | None = None
) -> str:
    now = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": ACCESS_AUDIENCE,
        "sub": str(claims.user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "jti": secrets.token_hex(8),
        "tenant_id": str(claims.tenant_id) if claims.tenant_id else None,
        "roles": claims.roles,
        "scopes": claims.scopes,
        "platform": claims.platform,
    }
    if claims.platform_access_reason:
        payload["platform_access_reason"] = claims.platform_access_reason
    return _encode(settings, payload)


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    claims = _decode(settings, token, ACCESS_AUDIENCE)
    try:
        tenant = claims.get("tenant_id")
        return AccessClaims(
            user_id=uuid.UUID(claims["sub"]),
            tenant_id=uuid.UUID(tenant) if tenant else None,
            roles=list(claims.get("roles", [])),
            scopes=list(claims.get("scopes", [])),
            platform=bool(claims.get("platform", False)),
            platform_access_reason=claims.get("platform_access_reason"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenError("invalid token claims") from exc


def issue_mfa_token(settings: Settings, user_id: uuid.UUID, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return _encode(
        settings,
        {
            "iss": settings.jwt_issuer,
            "aud": MFA_AUDIENCE,
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + MFA_TTL).timestamp()),
        },
    )


def decode_mfa_token(settings: Settings, token: str) -> uuid.UUID:
    return uuid.UUID(_decode(settings, token, MFA_AUDIENCE)["sub"])


def issue_device_token(
    settings: Settings, user_id: uuid.UUID, fingerprint: str, *, now: datetime | None = None
) -> str:
    """180 days of trust for this browser. The fingerprint binds the token to the current
    TOTP secret: resetting the second factor invalidates every remembered device."""
    now = now or datetime.now(UTC)
    return _encode(
        settings,
        {
            "iss": settings.jwt_issuer,
            "aud": DEVICE_AUDIENCE,
            "sub": str(user_id),
            "fp": fingerprint,
            "iat": int(now.timestamp()),
            "exp": int((now + DEVICE_TTL).timestamp()),
        },
    )


def decode_device_token(settings: Settings, token: str) -> tuple[uuid.UUID, str]:
    data = _decode(settings, token, DEVICE_AUDIENCE)
    return uuid.UUID(data["sub"]), str(data.get("fp", ""))


def issue_id_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    client_id: str,
    email: str,
    name: str,
    nonce: str | None,
    tenant_id: uuid.UUID | None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": client_id,
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "email": email,
        "name": name,
        "tenant_id": str(tenant_id) if tenant_id else None,
    }
    if nonce:
        payload["nonce"] = nonce
    return _encode(settings, payload)


def new_opaque_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return secrets.compare_digest(left, right)
