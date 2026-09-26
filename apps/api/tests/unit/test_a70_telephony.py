"""Telephony webhook helpers (A70): number normalisation, masking and signature window.
Expected values by hand."""

import time

from mhvp.communication import telephony as hook


def test_normalise_number_to_e164_or_raw() -> None:
    assert hook.normalise_number("0211 12345602") == ("+4921112345602", True)
    assert hook.normalise_number("+49 (0)151 2345 6789") == ("+4915123456789", True)
    assert hook.normalise_number("anonym") == ("anonym", False)
    assert hook.normalise_number("  12  ") == ("12", False)


def test_mask_number_keeps_country_code_and_last_two_digits() -> None:
    assert hook.mask_number("+4921112345699") == "+4921****99"
    assert hook.mask_number("0211123456") == "021****56"
    assert hook.mask_number("anonym") == "******"
    assert hook.mask_number("12") == "**"


def test_signature_window_and_format() -> None:
    body = b'{"event":"call.missed"}'
    now = int(time.time())
    sig = hook.sign("secret-of-tenant", now, body)
    assert sig.startswith("sha256=")
    assert hook.verify("secret-of-tenant", str(now), sig, body)
    assert not hook.verify("secret-of-tenant", str(now), sig, body + b" ")
    assert not hook.verify("other-secret", str(now), sig, body)
    stale = now - hook.WINDOW_SECONDS - 1
    assert not hook.verify(
        "secret-of-tenant", str(stale), hook.sign("secret-of-tenant", stale, body), body
    )
    assert not hook.verify("secret-of-tenant", "abc", sig, body)
    assert not hook.verify("secret-of-tenant", None, sig, body)
    assert not hook.verify("secret-of-tenant", str(now), "md5=abc", body)
