"""A56 (14, M21-01): configurable portal forms per tenant. The office maintains templates
(fields, audience, active); the portal lists only active templates of the own audience; a
submission creates a ticket of the template's category with the values as structured text and
own uploads as attachments; required fields and wrong types are refused (422); a second tenant
never sees the templates; the invitation carries a portal link when a portal URL is set."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.problems import ProblemError
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal import forms
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a56a-{RUN}", name=f"A56 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"a56b-{RUN}", name=f"A56 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("a56admin", a), ("a56adminb", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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
        settings = _settings(database, redis_url).model_copy(
            update={"web_portal_url": "https://portal.example.test/"}
        )
        with TestClient(create_app(settings)) as test_client:
            yield test_client


FIELDS = [
    {"key": "anliegen", "label": "Anliegen", "type": "text", "required": True},
    {"key": "personen", "label": "Anzahl Personen", "type": "number", "required": False},
    {"key": "ab", "label": "Ab dem", "type": "date", "required": True},
    {
        "key": "art",
        "label": "Art",
        "type": "select",
        "required": True,
        "options": ["Untervermietung", "Haustier"],
    },
    {"key": "nachweis", "label": "Nachweis", "type": "file", "required": False},
]


def _template(c: TestClient, h: dict[str, str], name: str, audience: str, **extra: Any) -> Any:
    body: dict[str, Any] = {
        "name": name,
        "category": "Antrag",
        "audience": audience,
        "fields": FIELDS,
        **extra,
    }
    return _ok(c.post(f"{PA}/forms", json=body, headers=h), 201)


def test_templates_submission_audience_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "a56admin"))
    hb = bearer(login(client, world, "a56adminb"))

    # Templates: one for tenants, one for owners, one inactive, one for all.
    for_tenants = _template(client, h, "Antrag Untervermietung", "tenant")
    _template(client, h, "Antrag bauliche Veränderung", "owner")
    _template(client, h, "Alte Vorlage", "all", active=False)
    for_all = _template(client, h, "Kontaktformular", "all", fields=[FIELDS[0]])
    assert for_tenants["fields"][3]["options"] == ["Untervermietung", "Haustier"]
    # Validation of the definition: select without options, duplicate key.
    bad = client.post(
        f"{PA}/forms",
        json={
            "name": "x",
            "category": "y",
            "fields": [
                {"key": "a", "label": "A", "type": "select"},
                {"key": "a", "label": "B", "type": "text"},
            ],
        },
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    assert {e["field"] for e in bad.json()["errors"]} == {"fields.0.options", "fields.1.key"}
    listed = _ok(client.get(f"{PA}/forms", headers=h))
    assert [t["name"] for t in listed] == [
        "Alte Vorlage",
        "Antrag Untervermietung",
        "Antrag bauliche Veränderung",
        "Kontaktformular",
    ]
    # Tenant B sees nothing of it and cannot change it.
    assert _ok(client.get(f"{PA}/forms", headers=hb)) == []
    assert (
        client.patch(f"{PA}/forms/{for_tenants['id']}", json={"active": False}, headers=hb)
    ).status_code == 404

    # A tenant (Mieter) with a portal account.
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "856", "name": "Formular-Haus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter56", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit(client, h, rental["id"], "56")
    party, _ = _party(client, h, "Mieter56")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    invitation = _ok(
        client.post(
            f"{PA}/accounts",
            json={
                "contact_id": _contact_of(client, h, contract["party_id"]),
                "email": world.email("a56link"),
                "display_name": "Link",
            },
            headers=h,
        ),
        201,
    )
    # A56: invitation link for the QR code in the CRM, built from the configured portal URL.
    assert invitation["invitation_url"].startswith("https://portal.example.test/einladung?code=")
    assert invitation["invitation_token"].split(".")[1] in invitation["invitation_url"]
    _ok(
        client.post(
            f"{P}/invitations/accept",
            json={"token": invitation["invitation_token"], "password": PASSWORD},
        )
    )
    ta = bearer(login(client, world, "a56link"))

    # The portal lists active templates of the own audience only, without CRM fields.
    visible = _ok(client.get(f"{P}/forms", headers=ta))
    assert [t["name"] for t in visible] == ["Antrag Untervermietung", "Kontaktformular"]
    assert "category" not in visible[0]
    owner_only = next(t for t in listed if t["audience"] == "owner")
    assert (
        client.post(
            f"{P}/forms/{owner_only['id']}/submissions", json={"values": {}}, headers=ta
        ).status_code
        == 404
    )

    # Required fields and types: 422 with field errors, no ticket.
    missing = client.post(
        f"{P}/forms/{for_tenants['id']}/submissions",
        json={"values": {"personen": "zwei", "ab": "31.12.2026", "art": "Sonstiges"}},
        headers=ta,
    )
    assert missing.status_code == 422, missing.text
    assert {e["field"] for e in missing.json()["errors"]} == {
        "values.anliegen",
        "values.personen",
        "values.ab",
        "values.art",
    }
    assert _ok(client.get(f"{P}/tickets", headers=ta)) == []

    # Own upload as attachment; a CRM document of the office is answered as not found.
    own = _ok(
        client.post(
            f"{P}/uploads",
            files={"file": ("nachweis.pdf", b"%PDF-1.4 nachweis", "application/pdf")},
            headers=ta,
        ),
        201,
    )
    office = _ok(
        client.post(
            "/api/v1/documents",
            data={"title": "Intern"},
            files={"file": ("intern.txt", b"intern", "text/plain")},
            headers=h,
        ),
        201,
    )
    values = {
        "anliegen": "Untervermietung an meine Schwester",
        "personen": "2",
        "ab": "2026-11-01",
        "art": "Untervermietung",
        "nachweis": [own["id"]],
    }
    assert (
        client.post(
            f"{P}/forms/{for_tenants['id']}/submissions",
            json={"values": {**values, "nachweis": [office["id"]]}},
            headers=ta,
        ).status_code
        == 404
    )
    # Unit of another contract is refused.
    assert (
        client.post(
            f"{P}/forms/{for_tenants['id']}/submissions",
            json={"values": values, "unit_id": "01920000-0000-7000-8000-000000000001"},
            headers=ta,
        ).status_code
        == 403
    )
    submitted = _ok(
        client.post(
            f"{P}/forms/{for_tenants['id']}/submissions",
            json={"values": values, "unit_id": unit},
            headers=ta,
        ),
        201,
    )
    ticket = _ok(client.get(f"/api/v1/tickets/{submitted['ticket_id']}", headers=h))
    assert ticket["category"] == "Antrag"
    assert ticket["title"] == "Antrag Untervermietung"
    assert ticket["source"] == "portal"
    assert ticket["unit_id"] == unit
    text = ticket["public_description"]
    assert "Formular: Antrag Untervermietung" in text
    assert "Anliegen: Untervermietung an meine Schwester" in text
    assert "Ab dem: 01.11.2026" in text
    assert "Art: Untervermietung" in text
    assert "Nachweis: nachweis.pdf" in text
    links = _ok(client.get(f"/api/v1/documents/{own['id']}", headers=h))["links"]
    assert any(
        link["entity_type"] == "ticket" and link["entity_id"] == submitted["ticket_id"]
        for link in links
    )
    # The portal user sees the Vorgang under Meldungen; tenant B never sees the ticket.
    mine = _ok(client.get(f"{P}/tickets", headers=ta))
    assert [t["id"] for t in mine] == [submitted["ticket_id"]]
    assert client.get(f"/api/v1/tickets/{submitted['ticket_id']}", headers=hb).status_code == 404

    # Empty submission of the contact form: required text missing -> 422; valid -> ticket.
    assert (
        client.post(f"{P}/forms/{for_all['id']}/submissions", json={"values": {}}, headers=ta)
    ).status_code == 422
    _ok(
        client.post(
            f"{P}/forms/{for_all['id']}/submissions",
            json={"values": {"anliegen": "Bitte um Rückruf"}},
            headers=ta,
        ),
        201,
    )
    # A used template cannot be deleted, only deactivated; deactivated forms leave the portal.
    assert client.delete(f"{PA}/forms/{for_all['id']}", headers=h).status_code == 409
    _ok(client.patch(f"{PA}/forms/{for_all['id']}", json={"active": False}, headers=h))
    assert [t["name"] for t in _ok(client.get(f"{P}/forms", headers=ta))] == [
        "Antrag Untervermietung"
    ]
    assert client.delete(f"{PA}/forms/{owner_only['id']}", headers=h).status_code == 204
    # Portal users have no management access.
    assert client.get(f"{PA}/forms", headers=ta).status_code == 403


def test_validate_values_pure() -> None:
    cleaned = forms.validate_values(
        forms.normalise_fields(FIELDS),
        {"anliegen": " x ", "ab": "2026-01-02", "art": "Haustier", "personen": "1,5"},
    )
    assert cleaned == {"anliegen": "x", "ab": "2026-01-02", "art": "Haustier", "personen": "1,5"}
    with pytest.raises(ProblemError) as excinfo:
        forms.validate_values(forms.normalise_fields(FIELDS), {"unbekannt": "x"})
    assert "values.unbekannt" in str(excinfo.value.errors)
