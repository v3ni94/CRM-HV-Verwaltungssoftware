"""AE32 (S711-10): Verzeichnis mit Rollen je Tätigkeit, Pflegefeldern ohne Vorbelegung,
Herkunft aus der Konfiguration, PDF-Export und Erkennung der Anbieter aus den Einstellungen."""

import asyncio
import uuid
from datetime import date
from typing import Any

from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.privacy import config_sources
from mhvp.privacy.config_sources import DetectedSource
from mhvp.privacy.models import PrivacyRegisterEntry
from mhvp.privacy.register_doc import blocks, render, render_pdf


def _entry(**kw: object) -> PrivacyRegisterEntry:
    base: dict[str, object] = {
        "id": uuid.uuid4(),
        "kind": "processor",
        "name": "Dienst A",
        "data_categories": [],
        "data_subjects": [],
        "third_country": False,
        "third_country_status": "open",
        "avv_status": "none",
        "legal_review_status": "open",
        "responsibilities": {},
        "processor_ids": [],
        "active": True,
    }
    return PrivacyRegisterEntry(**{**base, **kw})


def _src(key: str, name: str, active: bool = True) -> DetectedSource:
    return DetectedSource(key, name, "Testdienst", active, "Host test.example.", "tenant")


def test_activity_roles_legal_basis_and_processors() -> None:
    proc = _entry(name="Mailanbieter", kind="sub_processor", source_key="gmail")
    act = _entry(
        name="Eigentümerkommunikation",
        kind="processing_activity",
        responsibilities={"gdwe": "controller", "verwalter": "processor"},
        legal_basis="Eintrag Betreiber 1",
        processor_ids=[proc.id],
    )
    text = render("Mandant X", [proc, act], date(2026, 10, 1), [_src("gmail", "Google Gmail")])
    assert "Rolle GdWE (Gemeinschaft der Wohnungseigentümer): Verantwortlicher" in text
    assert "Rolle Verwalter: Auftragsverarbeiter" in text
    assert "Rolle Betreiber der Plattform: offen" in text
    assert "Rechtsgrundlage (Eintrag des Betreibers): Eintrag Betreiber 1" in text
    assert "Eingesetzte Auftragsverarbeiter: Mailanbieter" in text
    assert "Eigentümerkommunikation: Rolle offen für Betreiber der Plattform" in text
    assert "Herkunft: aus Konfiguration übernommen" in text
    assert "Alle erkannten Anbieter sind im Register erfasst." in text
    # no preset legal statement: empty fields read "offen", the platform names no norm
    assert "Art. 6" not in text
    assert "DSGVO Art" not in text
    assert chr(0x2014) not in text
    assert chr(0x2013) not in text


def test_open_fields_are_listed_as_gaps() -> None:
    act = _entry(name="Mieterportal", kind="processing_activity")
    proc = _entry(name="Druckdienst", kind="sub_processor", third_country_status="yes")
    gone = _entry(name="Altanbieter", kind="sub_processor", source_key="sms:alt.example")
    text = render(
        "Mandant", [act, proc, gone], date(2026, 10, 1), [_src("postal:letterxpress", "LXP")]
    )
    assert "Rechtsgrundlage (Eintrag des Betreibers): offen" in text
    assert "Mieterportal: Rechtsgrundlage nicht erfasst" in text
    assert "Mieterportal: Drittlandübermittlung ungeklärt" in text
    assert "Druckdienst: Drittlandübermittlung ohne dokumentierte Garantie" in text
    assert "LXP: laut Konfiguration genutzt, kein Registereintrag" in text
    assert "in der aktuellen Konfiguration nicht mehr gefunden" in text
    assert "3 Einträge ohne rechtliche Prüfung" in text


def test_third_country_no_and_countries() -> None:
    a = _entry(name="EU-Dienst", third_country_status="no")
    b = _entry(
        name="US-Dienst",
        third_country_status="yes",
        third_country=True,
        third_country_countries="USA",
        third_country_note="Garantie laut Betreiber",
    )
    text = render("M", [a, b], date(2026, 10, 1))
    assert "Drittland: nein (laut Eintrag)" in text
    assert "Drittland: ja, Länder: USA, Garantien: Garantie laut Betreiber" in text
    assert "EU-Dienst: Drittlandübermittlung ungeklärt" not in text
    # without detection there is no configuration section
    assert "Anbieter laut Konfiguration" not in text


def test_pdf_export_escapes_and_matches_blocks() -> None:
    e = _entry(name="A & B <Dienst>", purpose="Zweck <b>fett</b>")
    pdf = render_pdf("Mandant & Co", [e], date(2026, 10, 1), [])
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000
    assert any(b.text.startswith("A & B <Dienst>") for b in blocks("M", [e], date(2026, 10, 1)))


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def __iter__(self) -> Any:
        return iter(self.rows)


class _Session:
    """Answers every query with no rows: only platform settings contribute."""

    async def scalars(self, _stmt: Any) -> _Result:
        return _Result([])

    async def scalar(self, _stmt: Any) -> None:
        return None


def _settings(**kw: Any) -> Settings:
    # explicit values: the test environment may carry MHVP_S3_* and similar variables
    base: dict[str, Any] = {
        "s3_endpoint_url": None,
        "s3_access_key_id": None,
        "s3_secret_access_key": None,
        "objektakte_api_url": None,
        "objektakte_api_token": None,
        "objektakte_tenant": None,
        "otel_endpoint": None,
    }
    return Settings(
        database_url=SecretStr("postgresql+psycopg://x:y@localhost/db"),
        redis_url=SecretStr("redis://localhost:6379/0"),
        celery_broker_url=SecretStr("redis://localhost:6379/0"),
        **{**base, **kw},
    )


def test_detect_platform_settings_only_from_configuration() -> None:
    empty = asyncio.run(config_sources.detect(_Session(), _settings(), "hvm"))  # type: ignore[arg-type]
    assert empty == []
    s = _settings(
        s3_endpoint_url="https://s3.eu-central-1.example.com",
        s3_access_key_id=SecretStr("a"),
        s3_secret_access_key=SecretStr("b"),
        objektakte_api_url="https://objektakte.example.de/api/crm/v1/",
        objektakte_api_token=SecretStr("t"),
        objektakte_tenant="hvm",
    )
    found = asyncio.run(config_sources.detect(_Session(), s, "hvm"))  # type: ignore[arg-type]
    keys = {d.key for d in found}
    assert keys == {"s3:s3.eu-central-1.example.com", "objektakte"}
    assert all(d.scope == "platform" for d in found)
    # another tenant does not see the objektakte link of tenant "hvm"
    other = asyncio.run(config_sources.detect(_Session(), s, "tm"))  # type: ignore[arg-type]
    assert {d.key for d in other} == {"s3:s3.eu-central-1.example.com"}
    # no secret leaks into the detail
    assert all(d.detail != "t" and "SecretStr" not in d.detail_text for d in found)
