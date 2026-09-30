"""WebAuthn/passkeys as optional second factor (3.4, M2-03/S16-01), prepared, not active.

Operator decision 9 a of 30.09.2026: WebAuthn is offered as an optional second factor next to
TOTP (TOTP stays voluntary for non administrators). A verification library for attestation and
assertion (CBOR/COSE parsing, signature check, origin and RP ID binding, sign counter) is not
part of ``uv.lock``; writing that cryptography by hand would be an unreviewed security
component. Until a library is released (docs/OPEN_QUESTIONS.md, M2-03):

* ``AVAILABLE`` is ``False``; registration and assertion answer ``MHVP-AUTH-0012`` (503).
* The table ``webauthn_credential`` and the management endpoints (list, revoke) exist, so the
  API and the UI do not change shape when the library arrives.
* A WebAuthn credential never replaces the mandatory TOTP of administration users while
  ``AVAILABLE`` is ``False``.
"""

from mhvp.core.problems import ErrorCodes, ProblemError

AVAILABLE = False
UNAVAILABLE_REASON = (
    "Passkeys (WebAuthn) sind vorbereitet, aber noch nicht freigeschaltet: die "
    "Prüfbibliothek ist noch nicht freigegeben. Bitte TOTP als zweiten Faktor verwenden."
)


def ensure_available() -> None:
    if not AVAILABLE:
        raise ProblemError(ErrorCodes.WEBAUTHN_UNAVAILABLE, detail=UNAVAILABLE_REASON)
