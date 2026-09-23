"""Normalisation and validation of contact data (IBAN per ISO 13616, phone numbers E.164)."""

import re

import phonenumbers

_IBAN_LENGTHS = {
    "DE": 22,
    "AT": 20,
    "CH": 21,
    "NL": 18,
    "BE": 16,
    "FR": 27,
    "LU": 20,
    "IT": 27,
    "ES": 24,
}
_IBAN_SHAPE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")


class InvalidValueError(ValueError):
    pass


def normalise_iban(value: str) -> str:
    iban = re.sub(r"\s+", "", value).upper()
    if not _IBAN_SHAPE.fullmatch(iban):
        raise InvalidValueError("IBAN hat kein gültiges Format.")
    expected = _IBAN_LENGTHS.get(iban[:2])
    if expected is not None and len(iban) != expected:
        raise InvalidValueError(f"IBAN für {iban[:2]} muss {expected} Zeichen haben.")
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    if int(digits) % 97 != 1:
        raise InvalidValueError("IBAN-Prüfziffer ist falsch.")
    return iban


def mask_iban(iban: str) -> str:
    return f"{iban[:4]} **** **** {iban[-4:]}"


def normalise_phone(value: str, default_region: str = "DE") -> str:
    try:
        parsed = phonenumbers.parse(value, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidValueError("Telefonnummer ist nicht lesbar.") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidValueError("Telefonnummer ist ungültig.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
