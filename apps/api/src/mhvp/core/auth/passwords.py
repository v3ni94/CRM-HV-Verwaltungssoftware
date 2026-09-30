"""Password hashing (Argon2id) and policy (ASSUMPTIONS A-012, docs/rules/M2-05-passwortregeln.md).

Operator decision 9 a of 30.09.2026 (M2-05) replaces the decision of 26.09.2026 (minimum 6):
minimum length 12 characters and an offline check against compromised passwords
(``mhvp.core.auth.breached``, no network). The policy applies when a password is set or
changed; existing passwords keep working until they are changed. Maximum length, whitespace
rule and the lockout after 10 failed attempts for 15 minutes are unchanged.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from mhvp.core.auth import breached

MIN_LENGTH = 12
MAX_LENGTH = 128
MAX_FAILED_LOGINS = 10
LOCKOUT_MINUTES = 15

_hasher = PasswordHasher()  # argon2id with library defaults
# Verified against when the user does not exist, so timing does not reveal accounts.
_DUMMY_HASH = _hasher.hash("mhvp-timing-equaliser")


def policy_violation(password: str) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"Das Passwort muss mindestens {MIN_LENGTH} Zeichen lang sein."
    if len(password) > MAX_LENGTH:
        return f"Das Passwort darf höchstens {MAX_LENGTH} Zeichen lang sein."
    if password.strip() != password or not password.strip():
        return "Das Passwort darf nicht mit Leerzeichen beginnen oder enden."
    if breached.is_breached(password):
        return (
            "Dieses Passwort ist aus bekannten Datenlecks oder als häufig verwendet bekannt. "
            "Bitte wählen Sie ein anderes Passwort."
        )
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
