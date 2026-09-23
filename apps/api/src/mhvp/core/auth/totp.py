"""TOTP second factor (RFC 6238), mandatory for administration users (section 3.4)."""

import hmac
import time

import pyotp

ISSUER = "MH Verwaltungsplattform"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def matching_step(
    secret: str, code: str, *, last_step: int | None, now: float | None = None
) -> int | None:
    """Time step of a valid code (window +/- 1 step), newer than ``last_step``; else None."""
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return None
    totp = pyotp.TOTP(secret)
    current = int((now if now is not None else time.time()) // totp.interval)
    for step in (current - 1, current, current + 1):
        if (last_step is None or step > last_step) and hmac.compare_digest(
            totp.generate_otp(step), code
        ):
            return step
    return None
