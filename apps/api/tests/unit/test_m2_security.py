import base64
import time
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from pydantic import SecretStr

from mhvp.core import crypto
from mhvp.core.auth import passwords, tokens, totp
from mhvp.core.auth.permissions import ALL_PERMISSIONS, SYSTEM_ROLES, validate_permission
from mhvp.core.auth.principal import format_api_key, parse_api_key
from mhvp.core.config import Settings
from mhvp.core.webhooks import (
    RETRY_SCHEDULE_SECONDS,
    UnsafeWebhookTargetError,
    check_target,
    sign,
    verify,
)
from tests.conftest import make_settings


@pytest.fixture(autouse=True)
def _key() -> None:
    crypto.set_master_key(b"m" * 32)


def test_encryption_round_trip_and_scope_binding() -> None:
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    blob = crypto.encrypt("DE02120300000000202051", tenant_a)
    assert b"DE02" not in blob
    assert crypto.decrypt(blob, tenant_a) == "DE02120300000000202051"
    with pytest.raises(crypto.CryptoError, match="another scope"):
        crypto.decrypt(blob, tenant_b)
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(tampered, tenant_a)
    forged_header = blob.replace(tenant_a.encode(), tenant_b.encode())
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(forged_header, tenant_b)


def test_master_key_validation() -> None:
    assert crypto.decode_master_key(base64.b64encode(b"x" * 32).decode()) == b"x" * 32
    with pytest.raises(crypto.CryptoError):
        crypto.decode_master_key(base64.b64encode(b"short").decode())


def test_password_policy_and_hashing() -> None:
    assert passwords.policy_violation("short") is not None
    assert passwords.policy_violation(" leading space ok?") is not None
    assert passwords.policy_violation("a sufficiently long passphrase") is None
    hashed = passwords.hash_password("a sufficiently long passphrase")
    assert hashed.startswith("$argon2id$")
    assert passwords.verify_password(hashed, "a sufficiently long passphrase")
    assert not passwords.verify_password(hashed, "wrong")
    assert not passwords.verify_password(None, "anything")


def test_totp_window_and_replay() -> None:
    secret = totp.new_secret()
    now = time.time()
    step = int(now // 30)
    code = pyotp.TOTP(secret).generate_otp(step)
    assert totp.matching_step(secret, code, last_step=None, now=now) == step
    assert totp.matching_step(secret, code, last_step=step, now=now) is None
    assert totp.matching_step(secret, "12345", last_step=None, now=now) is None
    far = pyotp.TOTP(secret).generate_otp(step + 5)
    assert totp.matching_step(secret, far, last_step=None, now=now) is None


def _settings() -> Settings:
    return make_settings(
        jwt_private_key=SecretStr(tokens.generate_private_key_pem()), jwt_issuer="https://api.test"
    )


def test_access_token_round_trip_and_audience_separation() -> None:
    settings = _settings()
    user, tenant = uuid.uuid4(), uuid.uuid4()
    access = tokens.issue_access_token(
        settings, tokens.AccessClaims(user_id=user, tenant_id=tenant, roles=["x"])
    )
    claims = tokens.decode_access_token(settings, access)
    assert (claims.user_id, claims.tenant_id, claims.roles) == (user, tenant, ["x"])
    mfa = tokens.issue_mfa_token(settings, user)
    with pytest.raises(tokens.TokenError):
        tokens.decode_access_token(settings, mfa)
    expired = tokens.issue_access_token(
        settings,
        tokens.AccessClaims(user_id=user, tenant_id=None),
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    with pytest.raises(tokens.TokenError):
        tokens.decode_access_token(settings, expired)
    other = _settings()
    with pytest.raises(tokens.TokenError):
        tokens.decode_access_token(other, access)


def test_api_key_format() -> None:
    tenant = uuid.uuid4()
    key = format_api_key(tenant, "abc123", "s3cr3t_with_underscore")
    assert parse_api_key(key) == (tenant, "abc123", "s3cr3t_with_underscore")
    assert parse_api_key("mhvp_nothex_x_y") is None
    assert parse_api_key("other") is None


def test_webhook_signature() -> None:
    body = b'{"a":1}'
    header = sign("secret", body, 1_700_000_000)
    assert verify("secret", body, header, now=1_700_000_100)
    assert not verify("secret", body + b" ", header, now=1_700_000_100)
    assert not verify("secret", body, header, now=1_700_001_000)  # older than 5 minutes
    assert not verify("secret", body, "garbage", now=1_700_000_000)
    assert RETRY_SCHEDULE_SECONDS == (60, 300, 1800, 7200, 21600, 86400)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/x",
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://[::1]/x",
        "https://169.254.169.254/latest",
        "https://a:b@example.org",
        "file:///etc/passwd",
        "https://no-such-host.invalid/",
    ],
)
def test_webhook_targets_refused(url: str) -> None:
    with pytest.raises(UnsafeWebhookTargetError):
        check_target(url, allow_private=False)


def test_permissions_registry() -> None:
    validate_permission("tenant_settings:read")
    with pytest.raises(ValueError, match="unknown permission"):
        validate_permission("tenant_settings:print")
    for role in SYSTEM_ROLES:
        assert role.permissions <= ALL_PERMISSIONS
        assert "release_gates:approve" not in role.permissions  # only platform, four eyes


def test_pem_with_escaped_newlines_and_invalid_key() -> None:
    pem = tokens.generate_private_key_pem().replace("\n", "\\n")
    settings = make_settings(jwt_private_key=SecretStr(pem))
    assert tokens.public_jwk(settings)["crv"] == "P-256"
    with pytest.raises(tokens.TokenError):
        tokens.public_jwk(make_settings(jwt_private_key=SecretStr("change-me")))
