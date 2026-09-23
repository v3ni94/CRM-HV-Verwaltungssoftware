"""SEPA identifiers. Formats as used by the SEPA schemes; exact current scheme rules are an open
check (annex C.2 P05) before G2."""

import re

_CI = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{3}[A-Z0-9]{1,28}$")
# SEPA basic Latin character set, at most 35 characters.
_REFERENCE = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]{1,35}$")


class InvalidSepaValueError(ValueError):
    pass


def normalise_creditor_id(value: str) -> str:
    ci = re.sub(r"\s+", "", value).upper()
    if not _CI.fullmatch(ci):
        raise InvalidSepaValueError("Gläubiger-Identifikationsnummer hat kein gültiges Format.")
    country, check, national = ci[:2], ci[2:4], ci[7:]
    digits = "".join(str(int(ch, 36)) for ch in national + country + "00")
    if 98 - int(digits) % 97 != int(check):
        raise InvalidSepaValueError("Prüfziffer der Gläubiger-Identifikationsnummer ist falsch.")
    return ci


def check_mandate_reference(value: str) -> str:
    if not _REFERENCE.fullmatch(value):
        raise InvalidSepaValueError(
            "Mandatsreferenz: höchstens 35 Zeichen aus dem SEPA-Zeichensatz."
        )
    return value
