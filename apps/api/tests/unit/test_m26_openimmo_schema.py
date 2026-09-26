"""M26-02: schema check of the OpenImmo export (docs/rules/M26-02.md).

No official OpenImmo 1.2.7 XSD is bundled (licence, OpenImmo e.V.). The XSD code path is
exercised with a minimal test schema in tests/unit/fixtures and, because neither xmlschema
nor lxml is a dependency of the API, with an injected validator; the real lxml test is
skipped when the library is absent and reported as such by pytest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from mhvp.letting import openimmo, openimmo_schema

MINI_XSD = Path(__file__).parent / "fixtures" / "openimmo-mini.xsd"

VALID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<openimmo>
  <uebertragung art="CHANGE" umfang="TEIL" version="1.2.7"/>
  <anbieter>
    <firma>Hausverwaltung Test GmbH</firma>
    <immobilie>
      <objektkategorie>
        <nutzungsart WOHNEN="true" GEWERBE="false"/>
        <vermarktungsart KAUF="false" MIETE_PACHT="true"/>
        <objektart><wohnung/></objektart>
      </objektkategorie>
      <geo><plz>40001</plz><ort>Exportstadt</ort></geo>
      <verwaltung_techn>
        <objektnr_intern>0192abcd-0000-7000-8000-000000000060</objektnr_intern>
        <aktion aktionart="CHANGE"/>
      </verwaltung_techn>
    </immobilie>
  </anbieter>
</openimmo>
"""

# geo is missing: fails both the structural check and the mini XSD.
INVALID_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<openimmo>
  <uebertragung art="CHANGE" umfang="TEIL" version="1.2.7"/>
  <anbieter>
    <immobilie>
      <objektkategorie><objektart><wohnung/></objektart></objektkategorie>
      <verwaltung_techn>
        <objektnr_intern>x</objektnr_intern><aktion aktionart="CHANGE"/>
      </verwaltung_techn>
    </immobilie>
  </anbieter>
</openimmo>
"""


def _listing(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "id": UUID("0192abcd-0000-7000-8000-000000000060"),
        "kind": "rental",
        "object_type": "wohnung",
        "address_release": "vollstaendig",
        "price": Decimal("900.00"),
        "additional_costs": Decimal("150.00"),
        "heating_costs": None,
        "heating_in_additional_costs": False,
        "warm_rent": Decimal("1050.00"),
        "deposit": None,
        "living_area_sqm": Decimal("70.00"),
        "rooms": Decimal("3"),
        "features": {"balkon": True},
        "energy_status": "liegt_vor",
        "energy_type": "verbrauch",
        "energy_value": Decimal("80.00"),
        "energy_class": "C",
        "energy_valid_until": None,
        "energy_includes_hot_water": False,
        "energy_source": None,
        "energy_building_year": None,
        "energy_issued_on": None,
        "energy_note": None,
        "commission_note": None,
        "title": "Helle Wohnung",
        "description": "Mit Balkon.",
        "updated_at": datetime(2026, 9, 26, 10, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _property() -> Any:
    return SimpleNamespace(postal_code="40001", city="Exportstadt", street="Weg", house_number="9")


# Structural check (no XSD) ------------------------------------------------------------


def test_structure_check_passes_for_built_export() -> None:
    xml = openimmo.build_openimmo_xml(
        cast(Any, _listing()),
        cast(Any, _property()),
        cast(Any, SimpleNamespace()),
        contact=openimmo.ExportContact(company="HV Test", name="T. Test", email="t@example.org"),
        images=[openimmo.ExportImage("a.jpg", "image/jpeg", b"x", title="Front")],
    )
    result = openimmo_schema.validate_openimmo(xml, None)
    assert result.mode == "structure"
    assert result.valid is True
    assert result.errors == []
    assert result.xsd_configured is False
    assert result.notice == openimmo_schema.NOTICE_NO_XSD
    assert "XSD nicht hinterlegt" in (result.notice or "")


def test_structure_check_reports_documented_elements() -> None:
    errors = openimmo_schema.check_structure(INVALID_XML)
    assert "immobilie/geo fehlt." in errors
    assert "objektkategorie/nutzungsart fehlt." in errors
    assert "objektkategorie/vermarktungsart fehlt." in errors
    assert not any("verwaltung_techn" in e for e in errors)

    wrong_version = VALID_XML.replace(b'version="1.2.7"', b'version="1.2.6"')
    assert openimmo_schema.check_structure(wrong_version) == [
        "uebertragung/@version ist '1.2.6', erwartet '1.2.7'."
    ]
    assert openimmo_schema.check_structure(b"<foo/>") == [
        "Wurzelelement ist 'foo', erwartet 'openimmo'."
    ]
    assert openimmo_schema.check_structure(b"<openimmo><uebertragung") == [
        "Die XML-Datei ist nicht wohlgeformt."
    ]
    empty_objektart = VALID_XML.replace(b"<objektart><wohnung/></objektart>", b"<objektart/>")
    assert "objektkategorie/objektart enthält keine Objektart." in openimmo_schema.check_structure(
        empty_objektart
    )


def test_structure_check_result_serialises() -> None:
    result = openimmo_schema.validate_openimmo(INVALID_XML, None)
    assert result.valid is False
    data = result.to_dict()
    assert data["mode"] == "structure"
    assert data["valid"] is False
    assert "immobilie/geo fehlt." in data["errors"]
    assert data["notice"] == openimmo_schema.NOTICE_NO_XSD
    assert data["xsd_configured"] is False


# XSD configured -----------------------------------------------------------------------


def test_xsd_path_missing_falls_back_to_structure(tmp_path: Path) -> None:
    result = openimmo_schema.validate_openimmo(VALID_XML, str(tmp_path / "nope.xsd"))
    assert result.mode == "structure"
    assert result.valid is True
    assert result.notice == openimmo_schema.NOTICE_XSD_MISSING
    assert result.xsd_configured is True


def test_xsd_without_library_falls_back_to_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openimmo_schema, "_xmlschema_validator", lambda _p: None)
    monkeypatch.setattr(openimmo_schema, "_lxml_validator", lambda _p: None)
    result = openimmo_schema.validate_openimmo(INVALID_XML, str(MINI_XSD))
    assert result.mode == "structure"
    assert result.valid is False
    assert result.notice == openimmo_schema.NOTICE_NO_LIBRARY
    assert result.xsd_configured is True


def test_xsd_unloadable_falls_back_to_structure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.xsd"
    broken.write_text("<xs:schema")

    def boom(_p: Path) -> None:
        raise ValueError("bad schema")

    monkeypatch.setattr(openimmo_schema, "_xmlschema_validator", boom)
    result = openimmo_schema.validate_openimmo(VALID_XML, str(broken))
    assert result.mode == "structure"
    assert result.notice == openimmo_schema.NOTICE_XSD_INVALID


def test_xsd_validator_valid_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Injected validator (the XSD library is optional): a valid document passes, an
    invalid one lists the schema errors; no structural notice is attached."""
    seen: list[Path] = []

    def fake_validator(path: Path) -> openimmo_schema.Validator:
        seen.append(path)

        def validate(xml: bytes) -> list[str]:
            return [] if b"<geo>" in xml else ["Element 'immobilie': Missing child element geo."]

        return validate

    monkeypatch.setattr(openimmo_schema, "_xmlschema_validator", fake_validator)
    ok = openimmo_schema.validate_openimmo(VALID_XML, str(MINI_XSD))
    assert ok.mode == "xsd"
    assert ok.valid is True
    assert ok.errors == []
    assert ok.notice is None
    assert ok.xsd_configured is True
    assert seen == [MINI_XSD]

    bad = openimmo_schema.validate_openimmo(INVALID_XML, str(MINI_XSD))
    assert bad.mode == "xsd"
    assert bad.valid is False
    assert bad.errors == ["Element 'immobilie': Missing child element geo."]

    malformed = openimmo_schema.validate_openimmo(b"<openimmo>", str(MINI_XSD))
    assert malformed.mode == "xsd"
    assert malformed.errors == ["Die XML-Datei ist nicht wohlgeformt."]


def test_xsd_validator_exception_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(_path: Path) -> openimmo_schema.Validator:
        def validate(_xml: bytes) -> list[str]:
            raise RuntimeError("library crashed")

        return validate

    monkeypatch.setattr(openimmo_schema, "_xmlschema_validator", failing)
    result = openimmo_schema.validate_openimmo(VALID_XML, str(MINI_XSD))
    assert result.mode == "xsd"
    assert result.valid is False
    assert result.errors == ["Schemaprüfung fehlgeschlagen: library crashed"]


def test_xsd_validation_with_lxml_if_installed() -> None:
    """Real validation against the mini schema; skipped (reported as not executed) when
    lxml is not installed, which is the case for the API's own dependency set."""
    pytest.importorskip("lxml")
    validator = openimmo_schema._lxml_validator(MINI_XSD)
    assert validator is not None
    assert validator(VALID_XML) == []
    errors = validator(INVALID_XML)
    assert errors
    assert "geo" in errors[0]
