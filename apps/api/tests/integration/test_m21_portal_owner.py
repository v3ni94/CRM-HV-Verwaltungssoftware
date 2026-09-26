"""A51, section 14 role owner (read only): `GET /portal/resolutions` lists only announced
resolutions of the own community (a tally without announcement never appears),
`GET /portal/property-contacts` shows the manager and the caretaker released for owners
without private numbers, `GET /portal/hoa-account` shows posted lines of the owner's debtor
account in the community's ledger (drafts never, balance = charges minus credits). Tenants
are answered with 403; a portal user of another tenant sees nothing of this tenant."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal.owner import HOA_ACCOUNT_NOTE, LEGACY_NOTE, NO_LEDGER_NOTE
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
H = "/api/v1/hoa"
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"po51a-{RUN}", name=f"Eig A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"po51b-{RUN}", name=f"Eig B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("m21o_admin", a), ("m21o_admin_b", b)):
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=f"Verwalter {name}",
                password=PASSWORD,
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _portal_user(
    c: TestClient, h: dict[str, str], world: World, name: str, contact_id: str
) -> dict[str, str]:
    inv = _ok(
        c.post(
            f"{PA}/accounts",
            json={"contact_id": contact_id, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return bearer(login(c, world, name))


def _contact_of(c: TestClient, h: dict[str, str], party: str) -> str:
    return str(_ok(c.get(f"/api/v1/parties/{party}", headers=h))["members"][0]["contact_id"])


def _ownership(c: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )


def _weg(c: TestClient, h: dict[str, str], number: str, name: str) -> tuple[dict[str, Any], str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": name, "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    return prop, next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")


@dataclass
class OwnerWorld:
    admin: dict[str, str]
    owner1: dict[str, str]
    tenant: dict[str, str]
    owner_b: dict[str, str]
    property_number: str
    hoa: str
    contract_number: str
    announced_subject: str
    unannounced_subject: str
    external_subject: str


@pytest.fixture(scope="module")
def owner_world(client: TestClient, world: World) -> OwnerWorld:
    c = client
    h = bearer(login(c, world, "m21o_admin"))
    weg, hoa = _weg(c, h, "851", "A51 WEG Eigentuemerportal")
    _ok(
        c.put(
            f"/api/v1/properties/{weg['id']}",
            json={
                "number": "851",
                "name": "A51 WEG Eigentuemerportal",
                "management_type": "hoa",
                "street": "Portalstraße",
                "house_number": "5",
                "postal_code": "40721",
                "city": "Hilden",
                "manager_user_id": str(world.users["m21o_admin"]),
            },
            headers=h,
        )
    )
    unit01, unit02 = _unit(c, h, weg["id"], "01"), _unit(c, h, weg["id"], "02")
    owner1_party, _ = _party(c, h, "A51Eig01")
    owner2_party, _ = _party(c, h, "A51Eig02")
    o1 = _ownership(c, h, unit01, owner1_party)
    o2 = _ownership(c, h, unit02, owner2_party)

    # Contact persons: caretaker released for owners (work and private number), emergency
    # service not released in the master data.
    caretaker = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Hausmeisterdienst {RUN}",
                "phones": [
                    {"label": "work", "number": "+49 2103 111111", "is_primary": True},
                    {"label": "private", "number": "+49 171 2222222"},
                ],
            },
            headers=h,
        ),
        201,
    )
    emergency = _ok(
        c.post(
            "/api/v1/contacts",
            json={"kind": "company", "company_name": f"Notdienst intern {RUN}"},
            headers=h,
        ),
        201,
    )
    for contact, code, audience in (
        (caretaker, "caretaker", ["owner", "tenant"]),
        (emergency, "emergency", []),
    ):
        _ok(
            c.post(
                f"/api/v1/properties/{weg['id']}/contacts",
                json={
                    "contact_id": contact["id"],
                    "category_code": code,
                    "valid_from": "2020-01-01",
                    "visible_in_portal_for": audience,
                },
                headers=h,
            ),
            201,
        )

    # Owners' meeting (head principle): item 1 announced, item 2 tallied only.
    meeting = _ok(
        c.post(
            f"{H}/meetings",
            json={"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"},
            headers=h,
        ),
        201,
    )
    items = [
        _ok(
            c.post(
                f"{H}/meetings/{meeting['id']}/agenda",
                json={"title": title, "proposal": proposal},
                headers=h,
            ),
            201,
        )
        for title, proposal in (
            ("Sanierung Dach", "Das Dach wird saniert."),
            ("Fahrradkeller", "Der Fahrradkeller wird umgebaut."),
        )
    ]
    _ok(
        c.post(f"{H}/meetings/{meeting['id']}/invite", json={"invited_at": "2026-05-29"}, headers=h)
    )
    for contract in (o1, o2):
        _ok(
            c.post(
                f"{H}/meetings/{meeting['id']}/attendance",
                json={"contract_id": contract["id"], "present": True},
                headers=h,
            ),
            201,
        )
    for item in items:
        for contract in (o1, o2):
            _ok(
                c.post(
                    f"{H}/agenda/{item['id']}/votes",
                    json={"contract_id": contract["id"], "choice": "yes"},
                    headers=h,
                ),
                201,
            )
    _ok(c.get(f"{H}/agenda/{items[1]['id']}/tally", headers=h))  # proposal only
    _ok(
        c.post(
            f"{H}/agenda/{items[0]['id']}/announce",
            json={"outcome": "positive", "majority_basis": "einfache Mehrheit der Stimmen"},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": hoa,
                "decided_on": "2024-05-15",
                "subject": "Hausordnung 2024",
                "wording": "Die Hausordnung wird neu gefasst.",
                "status": "final",
                "kind": "external",
            },
            headers=h,
        ),
        201,
    )

    # Ledger of the community: one posted charge, one posted payment, one draft.
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(c.post(f"{A}/ledgers/{ledger}/sync-debtors", headers=h))
    accounts = _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    debtor1 = next(a["id"] for a in accounts if a["party_id"] == owner1_party)
    debtor2 = next(a["id"] for a in accounts if a["party_id"] == owner2_party)

    def entry(text: str, kind: str, day: str, lines: list[dict[str, str]], post: bool) -> None:
        row = _ok(
            c.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "booking_date": day,
                    "due_date": day,
                    "text": text,
                    "kind": kind,
                    "contract_id": o1["id"],
                    "lines": lines,
                },
                headers=h,
            ),
            201,
        )
        if post:
            _ok(c.post(f"{A}/ledgers/{ledger}/entries/{row['id']}/post", headers=h))

    entry(
        "Hausgeld Januar",
        "receivable",
        "2026-01-05",
        [
            {"account_id": debtor1, "debit": "250.00", "credit": "0.00"},
            {"account_id": debtor2, "debit": "0.00", "credit": "250.00"},
        ],
        post=True,
    )
    entry(
        "Zahlung Hausgeld",
        "debtor_payment",
        "2026-01-20",
        [
            {"account_id": debtor2, "debit": "100.00", "credit": "0.00"},
            {"account_id": debtor1, "debit": "0.00", "credit": "100.00"},
        ],
        post=True,
    )
    entry(
        "Entwurf Sonderumlage",
        "receivable",
        "2026-02-01",
        [
            {"account_id": debtor1, "debit": "999.00", "credit": "0.00"},
            {"account_id": debtor2, "debit": "0.00", "credit": "999.00"},
        ],
        post=False,
    )

    # Tenant of a rental property in the same tenant (no owner role).
    rental = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "852", "name": "A51 Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, "A51Vermieter", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit_a = _unit(c, h, rental["id"], "A")
    tenant_party, _ = _party(c, h, "A51Mieter")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_a,
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )

    # Another tenant with its own community and owner, without a ledger.
    hb = bearer(login(c, world, "m21o_admin_b"))
    weg_b, _ = _weg(c, hb, "861", "A51 Fremder Mandant")
    unit_b = _unit(c, hb, weg_b["id"], "01")
    owner_b_party, _ = _party(c, hb, "A51FremdEig")
    _ownership(c, hb, unit_b, owner_b_party)

    return OwnerWorld(
        admin=h,
        owner1=_portal_user(c, h, world, "m21o_owner1", _contact_of(c, h, owner1_party)),
        tenant=_portal_user(c, h, world, "m21o_tenant", _contact_of(c, h, tenant_party)),
        owner_b=_portal_user(c, hb, world, "m21o_owner_b", _contact_of(c, hb, owner_b_party)),
        property_number="851",
        hoa=hoa,
        contract_number=o1["number"],
        announced_subject="Sanierung Dach",
        unannounced_subject="Fahrradkeller",
        external_subject="Hausordnung 2024",
    )


def test_owner_sees_announced_resolutions_only(client: TestClient, owner_world: OwnerWorld) -> None:
    rows = _ok(client.get(f"{P}/resolutions", headers=owner_world.owner1))
    subjects = [r["subject"] for r in rows]
    assert owner_world.announced_subject in subjects
    assert owner_world.external_subject in subjects
    assert owner_world.unannounced_subject not in subjects
    announced = next(r for r in rows if r["subject"] == owner_world.announced_subject)
    assert announced["status"] == "positive"
    assert announced["kind"] == "meeting"
    assert announced["decided_on"] == "2026-06-20"
    assert announced["votes"] == {"principle": "head", "yes": "2", "no": "0", "abstain": "0"}
    assert announced["wording"] == "Das Dach wird saniert."
    external = next(r for r in rows if r["subject"] == owner_world.external_subject)
    assert (external["status"], external["kind"], external["votes"]) == ("final", "external", None)
    # Newest first.
    assert rows[0]["subject"] == owner_world.announced_subject
    # Only the own community: the list is scoped by the grants, never by a client id.
    assert {r["legal_entity_name"] for r in rows} == {rows[0]["legal_entity_name"]}


def test_property_contacts_show_manager_and_released_caretaker_only(
    client: TestClient, owner_world: OwnerWorld
) -> None:
    rows = _ok(client.get(f"{P}/property-contacts", headers=owner_world.owner1))
    assert [r["property_number"] for r in rows] == [owner_world.property_number]
    prop = rows[0]
    assert prop["manager_name"] == "Verwalter m21o_admin"
    assert prop["address"] == "Portalstraße 5, 40721 Hilden"
    assert [c["category"] for c in prop["contacts"]] == ["caretaker"]
    caretaker = prop["contacts"][0]
    assert caretaker["name"].startswith("Hausmeisterdienst")
    # Work number only; the private number is never part of the portal response.
    assert caretaker["phones"] == ["+492103111111"]
    assert "manager_user_id" not in prop
    assert "email" not in caretaker


def test_hoa_account_lists_posted_lines_only(client: TestClient, owner_world: OwnerWorld) -> None:
    body = _ok(client.get(f"{P}/hoa-account", headers=owner_world.owner1))
    assert body["note"] == HOA_ACCOUNT_NOTE
    # A new ledger keeps the legacy system as leading (M10 default): the same provisional
    # note as on /portal/account is shown until the ledger is switched to mhvp.
    assert body["legacy_note"] == LEGACY_NOTE
    assert len(body["contracts"]) == 1
    contract = body["contracts"][0]
    assert contract["contract_number"] == owner_world.contract_number
    assert contract["note"] is None
    assert [(e["text"], e["direction"], e["amount"]) for e in contract["entries"]] == [
        ("Hausgeld Januar", "charge", "250.00"),
        ("Zahlung Hausgeld", "credit", "100.00"),
    ]
    assert contract["entries"][0]["booking_date"] == "2026-01-05"
    assert contract["entries"][0]["reversed"] is False
    # 250,00 EUR charged minus 100,00 EUR paid = 150,00 EUR; the draft of 999,00 EUR is absent.
    assert (contract["charges"], contract["credits"], contract["balance"]) == (
        "250.00",
        "100.00",
        "150.00",
    )


@pytest.mark.parametrize("path", ["resolutions", "property-contacts", "hoa-account"])
def test_tenant_is_forbidden(client: TestClient, owner_world: OwnerWorld, path: str) -> None:
    assert client.get(f"{P}/{path}", headers=owner_world.tenant).status_code == 403


def test_foreign_tenant_sees_nothing_of_this_tenant(
    client: TestClient, owner_world: OwnerWorld
) -> None:
    assert _ok(client.get(f"{P}/resolutions", headers=owner_world.owner_b)) == []
    contacts = _ok(client.get(f"{P}/property-contacts", headers=owner_world.owner_b))
    assert [r["property_number"] for r in contacts] == ["861"]
    assert contacts[0]["manager_name"] is None
    assert contacts[0]["contacts"] == []
    account = _ok(client.get(f"{P}/hoa-account", headers=owner_world.owner_b))
    assert len(account["contracts"]) == 1
    assert account["contracts"][0]["note"] == NO_LEDGER_NOTE
    assert account["contracts"][0]["entries"] == []
    assert account["contracts"][0]["balance"] is None


def test_portal_owner_endpoints_need_no_crm_permission(
    client: TestClient, owner_world: OwnerWorld
) -> None:
    # The owner has no CRM right: the CRM resolution list of the same community is refused.
    assert (
        client.get(
            f"{H}/resolutions",
            params={"legal_entity_id": owner_world.hoa},
            headers=owner_world.owner1,
        ).status_code
        == 403
    )
