"""M8 acceptance with synthetic exports: staging, mapping templates with versions, validation
report, test run without effect, apply as import run, reconciliation, idempotent re-import with
conflicts, undo, staged-only journal. Column headers are invented for the test and make no
statement about real Immoware24 exports (13.1)."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from openpyxl import Workbook
from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-import"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BASE = "/api/v1/imports/immoware24"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"i-{RUN}", name=f"Import {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m8admin", "tenant_admin"), ("m8reader", "read_only")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _xlsx(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Export"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _stage(c: TestClient, h: dict[str, str], report: str, name: str, data: bytes, mime: str) -> Any:
    doc = _ok(c.post("/api/v1/documents", files={"file": (name, data, mime)}, headers=h))
    return _ok(
        c.post(f"{BASE}/files", json={"document_id": doc["id"], "report_type": report}, headers=h)
    )


def _mapping(
    c: TestClient,
    h: dict[str, str],
    report: str,
    columns: dict[str, str],
    value_maps: dict[str, dict[str, str]] | None = None,
) -> Any:
    return _ok(
        c.post(
            f"{BASE}/mappings",
            json={
                "report_type": report,
                "name": f"Standard {RUN}",
                "columns": columns,
                "value_maps": value_maps or {},
            },
            headers=h,
        )
    )


def _validate_apply(c: TestClient, h: dict[str, str], source: Any, mapping: Any) -> Any:
    _ok(
        c.post(
            f"{BASE}/files/{source['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        ),
        200,
    )
    return _ok(c.post(f"{BASE}/files/{source['id']}/apply", headers=h))


def test_import_assistant_end_to_end(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m8admin"))
    fields = _ok(client.get(f"{BASE}/fields", headers=h), 200)
    assert {f["name"] for f in fields["units"] if f["required"]} == {
        "property_number",
        "number",
        "unit_type",
    }

    props = _stage(
        client,
        h,
        "properties",
        "objekte.xlsx",
        _xlsx(
            [
                ["Objekt-Nr", "Bezeichnung", "Typ", "Straße", "Nr", "PLZ", "Ort"],
                ["801", "WEG Lindenweg", "WEG", "Lindenweg", "4", "40789", "Monheim am Rhein"],
                ["802", "Haus Markt", "Miete", "Am Markt", "1", "41812", "Erkelenz"],
                ["7", "Kaputt", "WEG", None, None, None, None],
            ]
        ),
        XLSX,
    )
    assert props["headers"] == ["Objekt-Nr", "Bezeichnung", "Typ", "Straße", "Nr", "PLZ", "Ort"]
    assert props["row_count"] == 3
    prop_cols = {
        "number": "Objekt-Nr",
        "name": "Bezeichnung",
        "management_type": "Typ",
        "street": "Straße",
        "house_number": "Nr",
        "postal_code": "PLZ",
        "city": "Ort",
    }
    missing_map = _mapping(client, h, "properties", prop_cols)
    checked = _ok(
        client.post(
            f"{BASE}/files/{props['id']}/validate",
            json={"mapping_id": missing_map["id"]},
            headers=h,
        ),
        200,
    )
    assert checked["report"]["validation"] == {
        "invalid": 3
    }  # "WEG" is not mapped to a platform value
    mapping = _mapping(
        client, h, "properties", prop_cols, {"management_type": {"WEG": "hoa", "Miete": "rental"}}
    )
    assert mapping["version"] == 2
    checked = _ok(
        client.post(
            f"{BASE}/files/{props['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        ),
        200,
    )
    assert checked["report"]["validation"] == {"valid": 2, "invalid": 1}
    invalid = _ok(
        client.get(f"{BASE}/files/{props['id']}/rows", params={"status": "invalid"}, headers=h), 200
    )
    assert invalid[0]["row_number"] == 4
    assert "nicht dreistellig" in invalid[0]["errors"][0]

    dry = _ok(client.post(f"{BASE}/files/{props['id']}/test-run", headers=h), 200)
    assert dry["counts"] == {"created": 2}
    assert _ok(client.get(f"{BASE}/overview", headers=h), 200)["properties"] == 0  # no effect
    applied = _ok(client.post(f"{BASE}/files/{props['id']}/apply", headers=h))
    assert applied["status"] == "applied"
    assert applied["report"]["reconciliation"]["open_differences"] == 1
    assert client.post(f"{BASE}/files/{props['id']}/apply", headers=h).status_code == 409

    units = _stage(
        client,
        h,
        "units",
        "einheiten.xlsx",
        _xlsx(
            [
                ["Objekt", "Einheit", "Art", "Fläche", "MEA", "MEA ab"],
                ["801", "01", "Wohnung", "71,35", "125,5", "01.01.2020"],
                ["801", "02", "Wohnung", "1.034,50", "98", "01.01.2020"],
                ["802", "01", "Wohnung", "55", None, None],
                ["803", "01", "Wohnung", "40", None, None],
                ["801", "03", "Wohnung", "abc", None, None],
            ]
        ),
        XLSX,
    )
    unit_map = _mapping(
        client,
        h,
        "units",
        {
            "property_number": "Objekt",
            "number": "Einheit",
            "unit_type": "Art",
            "living_area_sqm": "Fläche",
            "mea": "MEA",
            "mea_valid_from": "MEA ab",
        },
        {"unit_type": {"Wohnung": "apartment"}},
    )
    applied_units = _validate_apply(client, h, units, unit_map)
    assert applied_units["report"]["validation"] == {"valid": 4, "invalid": 1}
    assert applied_units["report"]["apply"]["counts"] == {"created": 3, "invalid": 1}  # 803 missing
    recon = applied_units["report"]["reconciliation"]
    assert recon["units_per_property"]["801"] == {"file": 3, "platform": 2, "difference": -1}

    contacts_csv = (
        "ID;Art;Anrede;Vorname;Name;Firma;Straße;PLZ;Ort;Telefon;E-Mail;IBAN\n"
        f"K1;P;Frau;Anna;Beispiel{RUN};;Lindenweg 4;40789;Monheim am Rhein;0171 1234567;anna.{RUN}@example.org;DE02120300000000202051\n"
        f"K2;P;;Bernd;Muster{RUN};;Am Markt 1;41812;Erkelenz;12;kaputt;\n"
        f"K3;F;;;;Vermietung {RUN} GmbH;;;;;;\n"
    ).encode()
    contacts = _stage(client, h, "contacts", "adressbuch.csv", contacts_csv, "text/csv")
    contact_map = _mapping(
        client,
        h,
        "contacts",
        {
            "external_id": "ID",
            "kind": "Art",
            "salutation": "Anrede",
            "first_name": "Vorname",
            "last_name": "Name",
            "company_name": "Firma",
            "street": "Straße",
            "postal_code": "PLZ",
            "city": "Ort",
            "phone": "Telefon",
            "email": "E-Mail",
            "iban": "IBAN",
        },
        {"kind": {"P": "person", "F": "company"}},
    )
    applied_contacts = _validate_apply(client, h, contacts, contact_map)
    assert applied_contacts["report"]["apply"]["counts"] == {"created": 3}
    problems = applied_contacts["report"]["apply"]["problems"]
    assert problems[0]["row"] == 3
    assert len(problems[0]["messages"]) == 2

    owners = _stage(
        client,
        h,
        "ownerships",
        "eigentuemer.xlsx",
        _xlsx(
            [
                ["Objekt", "Einheit", "Kontakt", "Beginn", "Grundbuch"],
                ["801", "01", "K1", "01.01.2020", "01.01.2020"],
                ["802", "01", "K3", "01.01.2019", "01.01.2019"],
            ]
        ),
        XLSX,
    )
    owner_map = _mapping(
        client,
        h,
        "ownerships",
        {
            "property_number": "Objekt",
            "unit_number": "Einheit",
            "contact_external_id": "Kontakt",
            "start_date": "Beginn",
            "title_transfer_date": "Grundbuch",
        },
    )
    applied_owners = _validate_apply(client, h, owners, owner_map)
    assert applied_owners["report"]["apply"]["counts"] == {
        "created": 2
    }  # contract and rental owner

    tenants = _stage(
        client,
        h,
        "tenancies",
        "mieter.xlsx",
        _xlsx(
            [
                ["Objekt", "Einheit", "Kontakt", "Beginn"],
                ["802", "01", "K2", "01.03.2021"],
                ["801", "01", "K2", "01.03.2021"],
            ]
        ),
        XLSX,
    )
    tenant_map = _mapping(
        client,
        h,
        "tenancies",
        {
            "property_number": "Objekt",
            "unit_number": "Einheit",
            "contact_external_id": "Kontakt",
            "start_date": "Beginn",
        },
    )
    applied_tenants = _validate_apply(client, h, tenants, tenant_map)
    assert applied_tenants["report"]["apply"]["counts"] == {
        "created": 1,
        "invalid": 1,
    }  # no tenancy in plain WEG

    payments = _stage(
        client,
        h,
        "payments",
        "zahlungen.xlsx",
        _xlsx(
            [
                ["Objekt", "Einheit", "Kontakt", "Vertrag", "Art", "Betrag", "USt", "ab"],
                ["802", "01", "K2", "Miete", "Miete", "650,00", "0", "01.03.2021"],
                ["801", "01", "K1", "Eigentum", "Hausgeld", "310,50", "0", "01.01.2020"],
                ["801", "01", "K1", "Eigentum", "Hausgeld", "-5,00", "0", "01.02.2020"],
            ]
        ),
        XLSX,
    )
    payment_map = _mapping(
        client,
        h,
        "payments",
        {
            "property_number": "Objekt",
            "unit_number": "Einheit",
            "contact_external_id": "Kontakt",
            "kind": "Vertrag",
            "payment_type_code": "Art",
            "gross": "Betrag",
            "vat_percent": "USt",
            "valid_from": "ab",
        },
        {
            "kind": {"Miete": "tenancy", "Eigentum": "ownership"},
            "payment_type_code": {"Miete": "rent", "Hausgeld": "hoa_fee"},
        },
    )
    applied_payments = _validate_apply(client, h, payments, payment_map)
    assert applied_payments["report"]["apply"]["counts"] == {"created": 2, "invalid": 1}
    assert applied_payments["report"]["apply"]["sums"] == {
        "source_gross": "955.50",
        "created_gross": "960.50",
    }

    overview = _ok(client.get(f"{BASE}/overview", headers=h), 200)
    assert overview["properties"] == 2
    assert overview["units"] == 3
    assert overview["contracts"] == 2

    # Re-import: nothing duplicated, differences reported as conflicts.
    again = _stage(
        client,
        h,
        "properties",
        "objekte2.xlsx",
        _xlsx(
            [
                ["Objekt-Nr", "Bezeichnung", "Typ", "Straße", "Nr", "PLZ", "Ort"],
                ["801", "WEG Lindenweg", "WEG", "Lindenweg", "4", "40789", "Monheim am Rhein"],
                ["802", "Haus Markt neu", "Miete", "Am Markt", "1", "41812", "Erkelenz"],
            ]
        ),
        XLSX,
    )
    re_applied = _validate_apply(client, h, again, mapping)
    assert re_applied["report"]["apply"]["counts"] == {"unchanged": 1, "conflict": 1}
    assert _ok(client.get(f"{BASE}/overview", headers=h), 200)["properties"] == 2

    journal = _stage(
        client,
        h,
        "journal",
        "journal.xlsx",
        _xlsx([["Datum", "Konto", "Betrag"], ["01.01.2024", "001200", "10,00"]]),
        XLSX,
    )
    journal_map = _mapping(client, h, "journal", {})
    staged = _validate_apply(client, h, journal, journal_map)
    assert staged["report"]["apply"]["counts"] == {}
    assert staged["report"]["validation"] == {"staged_only": 1}

    # Undo of the payments import removes only what that run created.
    undone = _ok(
        client.post(f"/api/v1/imports/{applied_payments['import_run_id']}/undo", headers=h), 200
    )
    assert undone["status"] == "undone"

    reader = bearer(login(client, world, "m8reader"))
    assert client.post(f"{BASE}/files/{props['id']}/apply", headers=reader).status_code == 403
