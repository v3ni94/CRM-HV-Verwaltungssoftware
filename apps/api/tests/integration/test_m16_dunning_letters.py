"""M16-10 object overrides of dunning settings (field level inheritance from the tenant
default) and M16-02 (partially) dunning letters as PDF drafts: sender is the managing company
of the tenant (tenant settings letterhead), fee and payment deadline only from configured
values, dispatch stays locked (G1 closed, and even with G1 open the send endpoint refuses).
Tenant separation: an override of tenant A is invisible to tenant B."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from pypdf import PdfReader

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import COMPANY

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
BUCKET = "mhvp-dunning-letters"


class OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=2_000_000,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dl-{RUN}", name=f"Mahnbrief {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dm-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("dladmin", a, "tenant_admin"),
            ("dlacc", a, "accountant_no_banking"),
            ("dlother", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def clients(
    database: Database, redis_url: str, s3: None
) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _debtor_contract(c: TestClient, h: dict[str, str], prop: str, unit_no: str) -> dict[str, Any]:
    """Ownership contract whose debtor has a complete postal address (letters need one)."""
    unit = _unit(c, h, prop, unit_no)
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Erika",
                "last_name": f"Schuldner{RUN}",
                "addresses": [
                    {
                        "street": "Rheinpromenade",
                        "house_number": "1",
                        "postal_code": "40789",
                        "city": "Monheim am Rhein",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    contract: dict[str, Any] = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party["id"],
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in [("hoa_fee", "300.00"), ("reserve", "50.00")]:
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2020-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    return contract


def _hoa_property(c: TestClient, h: dict[str, str], number: str, name: str) -> tuple[str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": name, "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    accounts = {
        a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, acc_no in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            c.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": accounts[acc_no]},
                headers=h,
            )
        )
    return prop["id"], ledger


TENANT_LEVELS = [
    {"level": 1, "min_days_overdue": 7, "text": "Zahlungserinnerung", "fee_amount": None},
    {"level": 2, "min_days_overdue": 14, "text": "1. Mahnung", "fee_amount": "5.00"},
]


def test_object_override_inherits_tenant_default(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """M16-10: an object row only stores what it overrides; every other field, and every
    omitted key of a level entry, comes from the tenant default. Removing the override makes
    the object inherit everything again."""
    client, _ = clients
    h = bearer(login(client, world, "dladmin"))
    prop, _ = _hoa_property(client, h, "771", "Mahnhaus Vererbung")

    # An override before the tenant default exists is refused.
    assert (
        client.put(
            f"{A}/dunning-settings",
            json={"property_id": prop, "threshold_amount": "50.00"},
            headers=h,
        ).status_code
        == 422
    )
    # The tenant default needs a ladder.
    assert (
        client.put(f"{A}/dunning-settings", json={"threshold_amount": "1"}, headers=h).status_code
        == 422
    )
    tenant = _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "levels": TENANT_LEVELS,
                "threshold_amount": "20.00",
                "fee_from_level": 2,
                "interest_enabled": False,
                "interest_spread": "5",
            },
            headers=h,
        )
    )
    assert tenant["sources"]["levels"] == "mandant"
    assert tenant["own"]["threshold_amount"] == "20.00"

    # Without an override the object reads the tenant default, marked as inherited.
    inherited = _ok(client.get(f"{A}/dunning-settings", params={"property_id": prop}, headers=h))
    assert inherited["own"] is None
    assert inherited["threshold_amount"] == "20.00"
    assert set(inherited["sources"].values()) == {"mandant"}

    # An override with no own value at all is refused.
    assert (
        client.put(f"{A}/dunning-settings", json={"property_id": prop}, headers=h).status_code
        == 422
    )

    # Override: own threshold and own ladder with a different deadline for level 2 and a
    # payment deadline; text and fee of level 2 are inherited from the tenant level 2.
    override = _ok(
        client.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop,
                "threshold_amount": "50.00",
                "levels": [
                    {"level": 1, "min_days_overdue": 3, "text": "Erinnerung Objekt"},
                    {"level": 2, "min_days_overdue": 21, "payment_days": 10},
                ],
            },
            headers=h,
        )
    )
    assert override["sources"] == {
        "levels": "objekt",
        "threshold_amount": "objekt",
        "fee_from_level": "mandant",
        "interest_enabled": "mandant",
        "interest_base_rate": "mandant",
        "interest_spread": "mandant",
    }
    assert override["threshold_amount"] == "50.00"
    assert override["fee_from_level"] == 2
    assert override["interest_spread"] == "5.00000000" or float(override["interest_spread"]) == 5
    level2 = next(lv for lv in override["levels"] if lv["level"] == 2)
    assert level2 == {
        "level": 2,
        "min_days_overdue": 21,
        "payment_days": 10,
        "text": "1. Mahnung",
        "fee_amount": "5.00",
    }
    assert override["own"]["fee_from_level"] is None  # stored as inherit, not copied
    assert override["own"]["interest_enabled"] is None

    listed = _ok(client.get(f"{A}/dunning-settings/overrides", headers=h))
    mine = next(o for o in listed if o["property_id"] == prop)
    assert mine["overridden_fields"] == ["levels", "threshold_amount"]

    # The tenant default is untouched by the override.
    default = _ok(client.get(f"{A}/dunning-settings", headers=h))
    assert default["threshold_amount"] == "20.00"
    assert default["levels"][0]["min_days_overdue"] == 7

    # Interest on the object cannot be switched on while the base rate is inherited as empty.
    assert (
        client.put(
            f"{A}/dunning-settings",
            json={"property_id": prop, "interest_enabled": True},
            headers=h,
        ).status_code
        == 422
    )

    # Remove the override: the object inherits again.
    assert (
        client.delete(f"{A}/dunning-settings", params={"property_id": prop}, headers=h).status_code
        == 204
    )
    assert (
        client.delete(f"{A}/dunning-settings", params={"property_id": prop}, headers=h).status_code
        == 404
    )
    again = _ok(client.get(f"{A}/dunning-settings", params={"property_id": prop}, headers=h))
    assert again["own"] is None
    assert again["threshold_amount"] == "20.00"


def test_override_is_tenant_separated(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, _ = clients
    h = bearer(login(client, world, "dladmin"))
    other = bearer(login(client, world, "dlother"))
    prop, _ = _hoa_property(client, h, "772", "Mahnhaus Trennung")
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={"levels": TENANT_LEVELS, "threshold_amount": "20.00", "interest_enabled": False},
            headers=h,
        )
    )
    _ok(
        client.put(
            f"{A}/dunning-settings",
            json={"property_id": prop, "threshold_amount": "99.00"},
            headers=h,
        )
    )
    foreign = _ok(client.get(f"{A}/dunning-settings", params={"property_id": prop}, headers=other))
    assert foreign["status"] == "nicht eingerichtet"
    assert foreign["own"] is None
    assert foreign["levels"] == []
    assert _ok(client.get(f"{A}/dunning-settings/overrides", headers=other)) == []
    assert (
        client.delete(
            f"{A}/dunning-settings", params={"property_id": prop}, headers=other
        ).status_code
        == 404
    )
    # The other tenant cannot write an override onto tenant A's property either
    # (no tenant default of its own, and the property is invisible).
    assert (
        client.put(
            f"{A}/dunning-settings",
            json={"property_id": prop, "threshold_amount": "1.00"},
            headers=other,
        ).status_code
        == 422
    )
    still = _ok(client.get(f"{A}/dunning-settings", params={"property_id": prop}, headers=h))
    assert still["threshold_amount"] == "99.00"


def test_letter_pdf_draft_and_send_locked(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """A dunning letter is generated as a PDF draft on the tenant letterhead (sender: the
    managing company), with the object's effective level text, configured fee and payment
    deadline, and is filed as a document linked to the case. Sending is refused with G1
    closed (gate) and with G1 open (dispatch not released, M16-02)."""
    client, gated = clients
    h = bearer(login(client, world, "dladmin"))
    gh = bearer(login(gated, world, "dladmin"))
    acc_user = bearer(login(gated, world, "dlacc"))
    prop, ledger = _hoa_property(gated, gh, "773", "Mahnhaus Brief")
    contract = _debtor_contract(gated, gh, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=gh), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=gh))
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 5, "text": "Zahlungserinnerung"},
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 1,
                "interest_enabled": False,
            },
            headers=gh,
        )
    )
    # Object override: own text, a configured fee and a payment deadline of 14 days.
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "property_id": prop,
                "levels": [
                    {
                        "level": 1,
                        "min_days_overdue": 5,
                        "text": "Erinnerung Objekt 773",
                        "fee_amount": "2.50",
                        "payment_days": 14,
                    }
                ],
            },
            headers=gh,
        )
    )
    preview = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=gh), 201)
    case = next(c for c in preview["cases"] if c["contract_id"] == contract["id"])
    assert case["status"] == "proposed"
    assert case["fee_amount"] == "2.50"

    # Without company data no letterhead, hence no letter (nothing is invented).
    incomplete = gated.post(f"{A}/dunning-cases/{case['id']}/letter-preview", headers=gh)
    assert incomplete.status_code == 422
    assert incomplete.json()["code"] == "MHVP-DOC-0004"
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=gh))

    pdf = gated.post(
        f"{A}/dunning-cases/{case['id']}/letter-preview",
        json={"letter_date": "2026-03-21"},
        headers=gh,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Hausverwaltung Müller GmbH" in text  # sender: managing company of the tenant
    assert "Erinnerung Objekt 773" in text  # effective level text from the object override
    assert "Entwurf" in text
    assert "350,00 EUR" in text
    assert "2,50 EUR" in text  # configured fee only
    assert "352,50 EUR" in text
    assert "04.04.2026" in text  # letter date plus configured payment_days
    assert "Verzugszinsen" not in text  # interest not configured, no line
    assert f"Sehr geehrte Frau Schuldner{RUN}" in text

    # Filing the draft links it to the case; the case itself stays "proposed".
    stored = _ok(gated.post(f"{A}/dunning-cases/{case['id']}/letter", headers=gh), 201)
    assert stored["letter_document_id"] is not None
    assert stored["status"] == "proposed"
    document = _ok(gated.get(f"/api/v1/documents/{stored['letter_document_id']}", headers=gh))
    assert document["mime_type"] == "application/pdf"
    assert "Entwurf" in document["title"]

    # Sending stays locked: G1 closed -> gate problem; G1 open -> still refused (M16-02).
    closed = client.post(f"{A}/dunning-cases/{case['id']}/letter/send", headers=h)
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    _ok(gated.post(f"{A}/dunning-runs/{preview['id']}/approve", headers=acc_user))
    locked = gated.post(f"{A}/dunning-cases/{case['id']}/letter/send", headers=gh)
    assert locked.status_code == 409
    assert "nicht freigegeben" in locked.json()["detail"]
    still = _ok(gated.get(f"{A}/dunning-runs/{preview['id']}", headers=gh))
    assert next(c for c in still["cases"] if c["id"] == case["id"])["status"] == "proposed"

    # Excluded cases get no letter; foreign tenants see nothing.
    other = bearer(login(gated, world, "dlother"))
    assert (
        gated.post(f"{A}/dunning-cases/{case['id']}/letter-preview", headers=other).status_code
        == 404
    )


def _pdf_text(response: Any) -> str:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_letter_text_modules_and_claim_table(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """A33: every level has a neutral standard text with the Forderungsaufstellung (Posten,
    Fälligkeit, Betrag, Summe); ``letter_text`` per level replaces the request paragraph and
    may use placeholders. ``{frist}`` only yields a date with ``payment_days``,
    ``{bankverbindung}`` falls back to "das Ihnen bekannte Konto" (M16-12, M16-13); unknown
    placeholders are refused when saving."""
    _, gated = clients
    gh = bearer(login(gated, world, "dladmin"))
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=gh))

    # Unknown placeholder: refused at save time, nothing is stored.
    bad = gated.put(
        f"{A}/dunning-settings",
        json={
            "levels": [
                {"level": 1, "min_days_overdue": 5, "text": "Erinnerung", "letter_text": "{frsit}"}
            ],
            "interest_enabled": False,
        },
        headers=gh,
    )
    assert bad.status_code == 422
    assert "frsit" in bad.json()["detail"]

    # Text preview with sample items: standard text of level 2 (1. Mahnung), no fee and no
    # deadline without values, table with the two sample items and the total.
    preview = _ok(gated.post(f"{A}/dunning-settings/letter-preview", json={"level": 2}, headers=gh))
    assert preview["hinweis"] == "Entwurf, kein Versand"
    assert preview["table"]["header"] == ["Posten", "Fälligkeit", "Betrag"]
    assert preview["table"]["rows"][-1] == ["Summe", "", "700,00 EUR"]
    assert preview["table"]["rows"][0] == ["Hausgeld Februar 2026", "03.02.2026", "350,00 EUR"]
    assert "trotz unserer Zahlungserinnerung" in preview["paragraphs"][1]
    request_paragraph = preview["paragraphs"][2]
    assert request_paragraph == (
        "Bitte überweisen Sie den Gesamtbetrag von 700,00 EUR auf das Ihnen bekannte Konto."
    )
    assert "Verzug" not in " ".join(preview["paragraphs"])
    assert "frist" in preview["placeholders"]
    assert "bankverbindung" in preview["placeholders"]

    # Own text with placeholders, a fee and a deadline of 10 days from the given letter date.
    custom = _ok(
        gated.post(
            f"{A}/dunning-settings/letter-preview",
            json={
                "level": 3,
                "text": "2. Mahnung Objekt",
                "letter_text": "Zahlen Sie {gesamtbetrag} {frist} {bankverbindung} ({stufe}).",
                "fee_amount": "7.50",
                "payment_days": 10,
                "letter_date": "2026-03-01",
            },
            headers=gh,
        )
    )
    assert custom["paragraphs"][2] == (
        "Zahlen Sie 707,50 EUR bis zum 11.03.2026 auf das Ihnen bekannte Konto (2. Mahnung Objekt)."
    )
    assert ["Mahngebühr laut hinterlegter Mahnstufe", "", "7,50 EUR"] in custom["table"]["rows"]
    assert custom["table"]["rows"][-1] == ["Summe", "", "707,50 EUR"]
    assert (
        gated.post(
            f"{A}/dunning-settings/letter-preview",
            json={"level": 1, "letter_text": "{konto}"},
            headers=gh,
        ).status_code
        == 422
    )

    # A real case: the stored letter_text of the level is used in the PDF, together with
    # the claim table.
    prop, ledger = _hoa_property(gated, gh, "774", "Mahnhaus Bausteine")
    contract = _debtor_contract(gated, gh, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=gh), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=gh))
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {
                        "level": 1,
                        "min_days_overdue": 5,
                        "text": "Zahlungserinnerung",
                        "letter_text": (
                            "Bitte gleichen Sie {gesamtbetrag} {frist} {bankverbindung} aus."
                        ),
                    }
                ],
                "threshold_amount": "20.00",
                "interest_enabled": False,
            },
            headers=gh,
        )
    )
    preview_run = _ok(
        gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=gh), 201
    )
    case = next(c for c in preview_run["cases"] if c["contract_id"] == contract["id"])
    text = _pdf_text(
        gated.post(
            f"{A}/dunning-cases/{case['id']}/letter-preview",
            json={"letter_date": "2026-03-21"},
            headers=gh,
        )
    )
    assert "Posten" in text
    assert "Fälligkeit" in text
    assert "Summe" in text
    assert "03.03.2026" in text  # due date of the March receivable (due day 3)
    assert "350,00 EUR" in text
    assert "Bitte gleichen Sie 350,00 EUR auf das Ihnen bekannte Konto aus." in text.replace(
        "\n", " "
    )
    assert "bis zum" not in text  # no payment_days configured, hence no date
    assert "Verzug" not in text
    assert "Entwurf" in text


def test_mahnbescheid_pdf_export(clients: tuple[TestClient, TestClient], world: World) -> None:
    """A31 (M16-07): the Mahnbescheid preparation is exported as a PDF on the tenant
    letterhead with the notice "Vorbereitung, Prüfung durch Rechtsanwalt erforderlich, kein
    Antrag", the claim table (Hauptforderung per item with due date, fee only once posted as
    a draft receivable, interest never), debtor, creditor and the dunning history. The export
    needs the preparation record first; the filed PDF is a generated document."""
    _, gated = clients
    gh = bearer(login(gated, world, "dladmin"))
    acc_user = bearer(login(gated, world, "dlacc"))
    _ok(gated.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=gh))
    prop, ledger = _hoa_property(gated, gh, "775", "Mahnhaus Bescheid")
    contract = _debtor_contract(gated, gh, prop, "01")
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    run = _ok(
        gated.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=gh), 201
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=gh))
    _ok(
        gated.put(
            f"{A}/dunning-settings",
            json={
                "levels": [
                    {"level": 1, "min_days_overdue": 5, "text": "Mahnung", "fee_amount": "5.00"}
                ],
                "threshold_amount": "20.00",
                "fee_from_level": 1,
                "interest_enabled": False,
            },
            headers=gh,
        )
    )
    preview = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-03-20"}, headers=gh), 201)
    case = next(c for c in preview["cases"] if c["contract_id"] == contract["id"])
    assert case["fee_amount"] == "5.00"

    # No export before the preparation record exists.
    early = gated.post(f"{A}/dunning-cases/{case['id']}/mahnbescheid-preview", headers=gh)
    assert early.status_code == 409

    # Approval posts the fee as a draft receivable; only then it counts as booked.
    _ok(gated.post(f"{A}/dunning-runs/{preview['id']}/approve", headers=acc_user))
    _ok(
        gated.post(
            f"{A}/dunning-cases/{case['id']}/mark-sent", json={"channel": "post"}, headers=gh
        )
    )
    prep = _ok(
        gated.post(f"{A}/dunning-cases/{case['id']}/mahnbescheid-vorbereitung", headers=gh), 201
    )

    text = _pdf_text(
        gated.post(
            f"{A}/dunning-cases/{case['id']}/mahnbescheid-preview",
            json={"letter_date": "2026-05-04"},
            headers=gh,
        )
    )
    flat = text.replace("\n", " ")
    assert "Vorbereitung, Prüfung durch Rechtsanwalt erforderlich, kein Antrag" in flat
    assert "Hausverwaltung Müller GmbH" in flat  # letterhead of the tenant
    assert "Gläubiger (Antragsteller)" in flat
    assert "Mahnhaus Bescheid" in flat
    assert f"Schuldner (Antragsgegner): Schuldner{RUN}, Erika" in flat
    assert "Rheinpromenade 1" in flat
    assert "Posten" in flat
    assert "Fälligkeit" in flat
    assert "03.03.2026" in flat
    assert "350,00 EUR" in flat
    assert "Mahngebühr laut hinterlegter Mahnstufe" in flat
    assert "5,00 EUR" in flat
    assert "355,00 EUR" in flat  # Summe: main claim plus the posted fee
    assert "Verzugszinsen sind nicht aufgenommen" in flat
    assert "Mahnhistorie" in flat
    assert "20.03.2026" in flat
    assert "versandt" in flat
    assert prep["aktenzeichen_intern"] in flat
    assert "Verzug wird nicht behauptet" in flat

    stored = _ok(gated.post(f"{A}/dunning-cases/{case['id']}/mahnbescheid", headers=gh), 201)
    assert stored["document_id"] is not None
    assert stored["status"] == "in_vorbereitung"
    document = _ok(gated.get(f"/api/v1/documents/{stored['document_id']}", headers=gh))
    assert document["mime_type"] == "application/pdf"
    assert "kein Antrag" in document["title"]

    other = bearer(login(gated, world, "dlother"))
    assert (
        gated.post(
            f"{A}/dunning-cases/{case['id']}/mahnbescheid-preview", headers=other
        ).status_code
        == 404
    )
