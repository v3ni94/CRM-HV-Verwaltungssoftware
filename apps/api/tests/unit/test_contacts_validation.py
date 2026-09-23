import pytest

from mhvp.contacts.validation import InvalidValueError, mask_iban, normalise_iban, normalise_phone


def test_iban_checksum_and_format() -> None:
    assert normalise_iban("de02 1203 0000 0000 2020 51") == "DE02120300000000202051"
    assert mask_iban("DE02120300000000202051") == "DE02 **** **** 2051"
    for bad in ("DE02120300000000202052", "DE0212030000000020205", "XX", "DE02-1203"):
        with pytest.raises(InvalidValueError):
            normalise_iban(bad)


def test_phone_normalisation() -> None:
    assert normalise_phone("02173 123456") == "+492173123456"
    assert normalise_phone("+43 1 234567") == "+431234567"
    with pytest.raises(InvalidValueError):
        normalise_phone("abc")
