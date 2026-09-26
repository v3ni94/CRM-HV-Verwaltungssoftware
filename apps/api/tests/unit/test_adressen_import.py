"""Addresses from property names and address list headers (mhvp.imports.adressen)."""

import pytest

from mhvp.imports import adressen


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Shalomweg 3", ("Shalomweg", "3")),
        ("Z ABGEGEBEN Brunnenstraße 145", ("Brunnenstraße", "145")),
        ("Y ABRECHNUNG Testweg 2a", ("Testweg", "2a")),
        ("WEG Am Panke Park 67-85", ("Am Panke Park", "67-85")),
        ("Am Panke Park 1-21 H1", ("Am Panke Park", "1-21 H1")),
        ("Gierlichsstraße 14", ("Gierlichsstraße", "14")),
        ("Garagenhof Nord", (None, None)),
        ("12 Häuser", (None, None)),
    ],
)
def test_derive_address(name: str, expected: tuple[str | None, str | None]) -> None:
    assert adressen.derive_address(name) == expected


def test_headers_tolerant() -> None:
    index = adressen.map_headers(["Objekt-Nummer", "Str.", "Nr.", "PLZ", "Stadt"])
    assert index == {"object": 0, "street": 1, "house_number": 2, "postal_code": 3, "city": 4}
    assert adressen.map_headers(["Objektnummer", "Strasse", "Ort"])["street"] == 1
    with pytest.raises(ValueError, match="Objektnummer"):
        adressen.map_headers(["Straße", "Ort"])


def test_object_number_raw_forms() -> None:
    assert adressen._object_number("82")[0] == "082"
    assert adressen._object_number("082")[0] == "082"
    assert adressen._object_number("82.0")[0] == "082"
    assert adressen._object_number("82 Shalomweg 3")[0] == "082"
