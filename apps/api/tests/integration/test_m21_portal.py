"""M21/M22 portals: invitation and password, access matrix (6.9.6) on list and download,
owners see GdWE administration documents but not another owner's or a tenant's files, tenants
only their contract documents released for tenants, other GdWE never; tickets and comments;
change proposals and meter readings are proposals decided by the management; providers see only
their work orders and document quote, appointment, execution and invoice submission; portal users
have no CRM access."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal import access
from mhvp.portal.staff_access import DEFAULT_STAFF_PORTAL_PERMISSIONS
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings

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
        a, _ = await services.provision_tenant(factory, slug=f"po-{RUN}", name=f"Portal {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m21admin"), display_name="admin", password=PASSWORD
        )
        world.users["m21admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(
    c: TestClient, h: dict[str, str], title: str, entity: str, entity_id: str, visibility: list[str]
) -> str:
    links = json.dumps([{"entity_type": entity, "entity_id": entity_id}])
    doc = _ok(
        c.post(
            "/api/v1/documents",
            data={"title": title, "links": links},
            files={"file": (f"{title}.txt", title.encode(), "text/plain")},
            headers=h,
        ),
        201,
    )
    _ok(c.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": visibility}, headers=h))
    return str(doc["id"])


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
    assert (
        c.post(
            f"{P}/invitations/accept",
            json={"token": inv["invitation_token"] + "x", "password": PASSWORD},
        ).status_code
        == 422
    )
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    assert (
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        ).status_code
        == 422
    )
    return bearer(login(c, world, name))


def _contact_of(c: TestClient, h: dict[str, str], party: str) -> str:
    return str(_ok(c.get(f"/api/v1/parties/{party}", headers=h))["members"][0]["contact_id"])


def test_portal_access_matrix(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m21admin"))
    weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "811", "name": "Portal-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    other_weg = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "813", "name": "Andere WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    other_hoa = next(e["id"] for e in other_weg["legal_entities"] if e["kind"] == "hoa")
    owners = {}
    for no in ("01", "02"):
        unit = _unit(client, h, weg["id"], no)
        party, _ = _party(client, h, f"Eig{no}")
        owners[no] = _ok(
            client.post(
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
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "812", "name": "Portal-Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    tenants = {}
    for no in ("A", "B"):
        unit = _unit(client, h, rental["id"], no)
        party, _ = _party(client, h, f"Mieter{no}")
        tenants[no] = _ok(
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

    gdwe = _doc(client, h, "Protokoll", "legal_entity", hoa, ["owner"])
    other = _doc(client, h, "Fremdprotokoll", "legal_entity", other_hoa, ["owner"])
    o2_file = _doc(client, h, "Kaufvertrag02", "contract", owners["02"]["id"], ["owner"])
    ta_file = _doc(client, h, "MietvertragA", "contract", tenants["A"]["id"], ["tenant"])
    ta_hidden = _doc(client, h, "InternA", "contract", tenants["A"]["id"], ["owner"])

    o1 = _portal_user(
        client, h, world, "m21owner1", _contact_of(client, h, owners["01"]["party_id"])
    )
    ta = _portal_user(
        client, h, world, "m21tenantA", _contact_of(client, h, tenants["A"]["party_id"])
    )
    me = _ok(client.get(f"{P}/me", headers=o1))
    assert me["roles"] == ["owner"]
    assert {d["id"] for d in _ok(client.get(f"{P}/documents", headers=o1))} == {gdwe}
    assert {d["id"] for d in _ok(client.get(f"{P}/documents", headers=ta))} == {ta_file}
    assert client.get(f"{P}/documents/{gdwe}/download", headers=o1).content == b"Protokoll"
    for forbidden in (other, o2_file, ta_file, ta_hidden):
        assert client.get(f"{P}/documents/{forbidden}/download", headers=o1).status_code == 404
    assert client.get(f"{P}/documents/{gdwe}/download", headers=ta).status_code == 404
    assert client.get("/api/v1/contacts", headers=ta).status_code == 403  # no CRM access
    assert client.get("/api/v1/accounting/ledgers", headers=o1).status_code == 403

    # Tickets and comments within the own scope.
    unit_a = tenants["A"]["unit_id"]
    assert (
        client.post(
            f"{P}/tickets",
            json={
                "title": "Fenster klemmt",
                "description": "Küche",
                "unit_id": tenants["B"]["unit_id"],
            },
            headers=ta,
        ).status_code
        == 403
    )
    ticket = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Fenster klemmt", "description": "Küche", "unit_id": unit_a},
            headers=ta,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": "intern", "internal": True},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/comments",
            json={"body": "Handwerker kommt", "internal": False},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(f"{P}/tickets/{ticket['id']}/comments", json={"body": "Danke"}, headers=ta), 201
    )
    mine = _ok(client.get(f"{P}/tickets", headers=ta))
    assert mine[0]["comments"] == ["Handwerker kommt", "Danke"]
    assert (
        client.post(
            f"{P}/tickets/{ticket['id']}/comments", json={"body": "x"}, headers=o1
        ).status_code
        == 404
    )

    # Proposals: never self approved.
    change = _ok(
        client.post(
            f"{P}/change-requests",
            json={"kind": "phone", "payload": {"number": "+49211123456"}},
            headers=ta,
        ),
        201,
    )
    bank = _ok(
        client.post(
            f"{P}/change-requests",
            json={"kind": "bank_account", "payload": {"iban": "DE89370400440532013000"}},
            headers=ta,
        ),
        201,
    )
    meter = _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/meters",
            json={
                "unit_id": unit_a,
                "meter_type_code": "cold_water",
                "number": f"KW-{RUN}",
                "valid_from": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    reading = _ok(
        client.post(
            f"{P}/meter-readings",
            json={"meter_id": meter["id"], "value": "123.4", "read_at": "2026-09-20"},
            headers=ta,
        ),
        201,
    )
    queue = {r["id"]: r for r in _ok(client.get(f"{PA}/change-requests", headers=h))}
    assert queue[bank["id"]]["status"] == "proposed"
    _ok(
        client.post(f"{PA}/change-requests/{change['id']}/decide", json={"accept": True}, headers=h)
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{reading['id']}/decide", json={"accept": True}, headers=h
        )
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{bank['id']}/decide",
            json={"accept": False, "note": "Nachweis fehlt"},
            headers=h,
        )
    )
    assert (
        client.post(
            f"{PA}/change-requests/{bank['id']}/decide", json={"accept": True}, headers=h
        ).status_code
        == 409
    )
    assert _ok(client.get(f"{P}/account", headers=ta))["items"] == []

    # Provider portal (M22).
    provider_contact = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Glaser {RUN}"}, headers=h
        ),
        201,
    )["id"]
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": rental["id"],
                "provider_contact_id": provider_contact,
                "description": "Fenster richten",
                "budget_limit": "500",
            },
            headers=h,
        ),
        201,
    )
    foreign = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "property_id": rental["id"],
                "provider_contact_id": _ok(
                    client.post(
                        "/api/v1/contacts",
                        json={"kind": "company", "company_name": f"Andere {RUN}"},
                        headers=h,
                    ),
                    201,
                )["id"],
                "description": "Fremd",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/work-orders/{order['id']}/steps", json={"status": "requested"}, headers=h
        )
    )
    pv = _portal_user(client, h, world, "m21provider", provider_contact)
    assert _ok(client.get(f"{P}/me", headers=pv))["roles"] == ["provider"]
    assert [o["id"] for o in _ok(client.get(f"{P}/work-orders", headers=pv))] == [order["id"]]
    assert (
        client.post(
            f"{P}/work-orders/{foreign['id']}/quote", json={"amount": "10"}, headers=pv
        ).status_code
        == 404
    )
    offer = _ok(
        client.post(
            f"{P}/uploads",
            files={"file": ("angebot.pdf", b"%PDF-1.4 angebot", "application/pdf")},
            headers=pv,
        ),
        201,
    )
    # Review 1.22 Nr. 16: only an own upload may be referenced as the quote document.
    assert (
        client.post(
            f"{P}/work-orders/{order['id']}/quote",
            json={"amount": "350.00", "document_id": str(uuid.uuid4())},
            headers=pv,
        ).status_code
        == 404
    )
    _ok(
        client.post(
            f"{P}/work-orders/{order['id']}/quote",
            json={"amount": "350.00", "document_id": offer["id"]},
            headers=pv,
        )
    )
    assert (
        client.post(
            f"{P}/work-orders/{order['id']}/appointment",
            json={"scheduled_at": "2026-10-02T09:00:00Z"},
            headers=pv,
        ).status_code
        == 409
    )  # not approved yet
    _ok(
        client.post(
            f"/api/v1/work-orders/{order['id']}/steps", json={"status": "approved"}, headers=h
        )
    )
    _ok(
        client.post(
            f"{P}/work-orders/{order['id']}/appointment",
            json={"scheduled_at": "2026-10-02T09:00:00Z"},
            headers=pv,
        )
    )
    assert (
        client.post(
            f"{P}/work-orders/{order['id']}/invoice",
            json={
                "number": "G-1",
                "invoice_date": "2026-10-03",
                "gross": "350.00",
                "document_id": offer["id"],
            },
            headers=pv,
        ).status_code
        == 409
    )
    done = _ok(
        client.post(
            f"{P}/work-orders/{order['id']}/complete",
            json={"report": "Beschlag ersetzt"},
            headers=pv,
        )
    )
    assert done["status"] == "done"
    sub = _ok(
        client.post(
            f"{P}/work-orders/{order['id']}/invoice",
            json={
                "number": "G-1",
                "invoice_date": "2026-10-03",
                "gross": "350.00",
                "document_id": offer["id"],
            },
            headers=pv,
        ),
        201,
    )
    assert sub["kind"] == "invoice_submission"
    assert client.get("/api/v1/tickets", headers=pv).status_code == 403


def test_staff_portal_sees_tenant_wide_data_per_matrix(client: TestClient, world: World) -> None:
    """Operator decision 25.09.2026 (M2-08 entschieden, docs/rules/M2-07.md): a staff member
    (CRM role "standard") automatically gets portal access and sees every document and ticket
    of the tenant, not only ones linked to a contract of their own, because the portal
    permission matrix grants "documents:read" and "tickets:read" to that role by default."""
    h = bearer(login(client, world, "m21admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "899", "name": "Staff-Test", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    doc_id = _doc(client, h, "Interne Notiz", "property", prop["id"], ["owner", "tenant"])
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Heizung defekt", "priority": "normal"},
            headers=h,
        ),
        201,
    )
    email = f"m21staff-{RUN}@example.org"
    _ok(
        client.post(
            "/api/v1/tenant/members",
            json={
                "email": email,
                "display_name": "M21 Staff",
                "password": PASSWORD,
                "role_codes": ["standard"],
            },
            headers=h,
        ),
        201,
    )
    login_step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login_step.status_code == 200, login_step.text
    staff = {"Authorization": f"Bearer {login_step.json()['access_token']}"}
    docs = _ok(client.get(f"{P}/documents", headers=staff))
    assert any(d["id"] == doc_id for d in docs)
    tickets = _ok(client.get(f"{P}/tickets", headers=staff))
    assert any(t["id"] == ticket["id"] for t in tickets)
    me = _ok(client.get(f"{P}/me", headers=staff))
    assert me["roles"] == ["staff"]
    assert me["contracts"] == []
    assert me["permissions"] == sorted(DEFAULT_STAFF_PORTAL_PERMISSIONS["standard"])


def test_me_never_500_for_bare_contact_without_grants(client: TestClient, world: World) -> None:
    """A portal account with a contact but no contract and no access grant (a bare contact
    invited by mistake, or one whose contract ended and whose grants expired) must still get
    a plain empty answer from /me, never a 500 (Playwright finding, 2026-09-25)."""
    h = bearer(login(client, world, "m21admin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Bare", "last_name": f"Contact-{RUN}"},
            headers=h,
        ),
        201,
    )
    bare = _portal_user(client, h, world, "m21bare", contact["id"])
    me = _ok(client.get(f"{P}/me", headers=bare))
    assert me["roles"] == []
    assert me["contracts"] == []
    assert me["permissions"] == []


# A22: acceptance cases D29 to D31 (6.9.6, 14, E06) per access path -----------------------------
#
# One module wide world (documents live in the moto bucket of one client, so a module scoped
# client keeps the blobs alive for every parametrized case). Portal users hold no CRM permission,
# therefore every CRM side path (search, single read, original download, links, bulk export)
# answers 403; the portal side paths (list, download) answer without a hint whether a foreign
# document exists (404).


@dataclass
class AccessWorld:
    admin: dict[str, str]
    owner1: dict[str, str]
    tenant_a: dict[str, str]
    tenant_b: dict[str, str]
    docs: dict[str, str]
    titles: dict[str, str]


@pytest.fixture(scope="module")
def access_client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ownership(
    c: TestClient, h: dict[str, str], unit: str, party: str, sev: bool = False
) -> dict[str, Any]:
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
                "sev_enabled": sev,
            },
            headers=h,
        ),
        201,
    )


def _tenancy(c: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
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


@pytest.fixture(scope="module")
def access_world(access_client: TestClient, world: World) -> AccessWorld:
    c = access_client
    h = bearer(login(c, world, "m21admin"))
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "821", "name": "D29-WEG", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    other_weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "823", "name": "D30-Fremde-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    rental = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "822", "name": "D31-Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    other_hoa = next(e["id"] for e in other_weg["legal_entities"] if e["kind"] == "hoa")
    unit01, unit02 = _unit(c, h, weg["id"], "01"), _unit(c, h, weg["id"], "02")
    owner1_party, _ = _party(c, h, "D29Eig01")
    owner2_party, _ = _party(c, h, "D29Eig02")
    sev_tenant_party, _ = _party(c, h, "D30SevMieter")
    _ownership(c, h, unit01, owner1_party)
    o2 = _ownership(c, h, unit02, owner2_party, sev=True)
    sev = _tenancy(c, h, unit02, sev_tenant_party)  # owner 02 lets unit 02: private SEV file
    landlord, _ = _party(c, h, "D31Vermieter", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit_a, unit_b = _unit(c, h, rental["id"], "A"), _unit(c, h, rental["id"], "B")
    tenant_a_party, _ = _party(c, h, "D31MieterA")
    tenant_b_party, _ = _party(c, h, "D31MieterB")
    ta = _tenancy(c, h, unit_a, tenant_a_party)
    _tenancy(c, h, unit_b, tenant_b_party)

    titles = {
        "beschluss": f"Beschlusssammlung {RUN}",
        "protokoll": f"Versammlungsprotokoll {RUN}",
        "wirtschaftsplan": f"Wirtschaftsplan {RUN}",
        "fremde_gdwe": f"Fremdbeschluss {RUN}",
        "sev_vertrag": f"SEV Mietvertrag 02 {RUN}",
        "sev_akte": f"SEV Akte 02 {RUN}",
        "o2_kaufvertrag": f"Kaufvertrag 02 {RUN}",
        "beleg_original": f"Heizkostenrechnung {RUN}",
        "beleg_freigabe": f"Heizkostenrechnung geschwaerzt {RUN}",
    }
    docs = {
        # D29: administrative documents of the GdWE, linked to the legal entity only.
        "beschluss": _doc(c, h, titles["beschluss"], "legal_entity", hoa, ["owner"]),
        "protokoll": _doc(c, h, titles["protokoll"], "legal_entity", hoa, ["owner"]),
        "wirtschaftsplan": _doc(c, h, titles["wirtschaftsplan"], "legal_entity", hoa, ["owner"]),
        # D30: another community, the private SEV file of owner 02 in the same community and
        # the purchase contract of owner 02.
        "fremde_gdwe": _doc(c, h, titles["fremde_gdwe"], "legal_entity", other_hoa, ["owner"]),
        "sev_vertrag": _doc(
            c, h, titles["sev_vertrag"], "contract", sev["id"], ["tenant", "owner"]
        ),
        "sev_akte": _doc(c, h, titles["sev_akte"], "unit", unit02, ["owner"]),
        "o2_kaufvertrag": _doc(c, h, titles["o2_kaufvertrag"], "contract", o2["id"], ["owner"]),
        # D31: the receipt with third party data stays on the property; the released version
        # is linked to tenant A's contract and to its original (entity_type "document").
        "beleg_original": _doc(
            c, h, titles["beleg_original"], "property", rental["id"], ["tenant"]
        ),
        "beleg_freigabe": _doc(c, h, titles["beleg_freigabe"], "contract", ta["id"], ["tenant"]),
    }
    _ok(
        c.post(
            f"/api/v1/documents/{docs['beleg_freigabe']}/links",
            json={
                "entity_type": "document",
                "entity_id": docs["beleg_original"],
                "role": "generated",
            },
            headers=h,
        ),
        201,
    )
    return AccessWorld(
        admin=h,
        owner1=_portal_user(c, h, world, "m21d_owner1", _contact_of(c, h, owner1_party)),
        tenant_a=_portal_user(c, h, world, "m21d_tenant_a", _contact_of(c, h, tenant_a_party)),
        tenant_b=_portal_user(c, h, world, "m21d_tenant_b", _contact_of(c, h, tenant_b_party)),
        docs=docs,
        titles=titles,
    )


def _portal_ids(c: TestClient, h: dict[str, str]) -> set[str]:
    return {d["id"] for d in _ok(c.get(f"{P}/documents", headers=h))}


# Every access path of the matrix (6.9.6: UI, API, downloads, RAG search, exports). Each entry
# returns True when the path denies the document for the given portal user.
def _denied_portal_list(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    return doc not in _portal_ids(c, h)


def _denied_portal_download(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    return c.get(f"{P}/documents/{doc}/download", headers=h).status_code == 404


def _denied_crm_read(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    return c.get(f"/api/v1/documents/{doc}", headers=h).status_code == 403


def _denied_crm_download(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    return c.get(f"/api/v1/documents/{doc}/content", headers=h).status_code == 403


def _denied_crm_search(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    return c.get("/api/v1/documents", params={"q": title}, headers=h).status_code == 403


def _denied_crm_link(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    body = {"entity_type": "document", "entity_id": doc, "role": "attachment"}
    return c.post(f"/api/v1/documents/{doc}/links", json=body, headers=h).status_code == 403


def _denied_bulk_export(c: TestClient, h: dict[str, str], doc: str, title: str) -> bool:
    # No document bulk export exists for portal users; the CRM wide listing and the only ZIP
    # export of the API (listings, M26) are the bulk paths a portal token could try.
    listing = c.get("/api/v1/documents", headers=h)
    archive = c.get("/api/v1/letting/listings/openimmo.zip", headers=h)
    assert (listing.status_code, archive.status_code) == (403, 403), (listing.text, archive.text)
    return True


PATHS = {
    "portal_list": _denied_portal_list,
    "portal_download": _denied_portal_download,
    "crm_read": _denied_crm_read,
    "crm_download": _denied_crm_download,
    "crm_search": _denied_crm_search,
    "crm_link": _denied_crm_link,
    "bulk_export": _denied_bulk_export,
}


@pytest.mark.parametrize("kind", ["beschluss", "protokoll", "wirtschaftsplan"])
def test_d29_owner_sees_gdwe_documents_outside_own_statement(
    access_client: TestClient, access_world: AccessWorld, kind: str
) -> None:
    """D29: the documents are linked to the GdWE only, not to the owner's unit or contract;
    the member right (§ 18 Abs. 4 WEG, hoa_member_right) opens list and download."""
    doc = access_world.docs[kind]
    assert doc in _portal_ids(access_client, access_world.owner1)
    response = access_client.get(f"{P}/documents/{doc}/download", headers=access_world.owner1)
    assert response.status_code == 200, response.text
    assert response.content == access_world.titles[kind].encode()
    assert "X-Redaction-Note" not in response.headers


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("kind", ["fremde_gdwe", "sev_vertrag", "sev_akte", "o2_kaufvertrag"])
def test_d30_foreign_gdwe_and_sev_files_denied_on_every_path(
    access_client: TestClient, access_world: AccessWorld, kind: str, path: str
) -> None:
    """D30: the same owner gets no access to another community, to the private SEV file of
    another owner in the own community or to another owner's contract file, over any path.
    The AI context path is covered in test_m7_ai.py (test_d30_ai_context_excludes_foreign_documents)."""
    assert PATHS[path](
        access_client, access_world.owner1, access_world.docs[kind], access_world.titles[kind]
    )


@pytest.mark.parametrize("path", sorted(PATHS))
def test_d31_tenant_never_reaches_the_unredacted_receipt(
    access_client: TestClient, access_world: AccessWorld, path: str
) -> None:
    """D31: the receipt with third party data is not released as a whole (no Vollfreigabe)."""
    assert PATHS[path](
        access_client,
        access_world.tenant_a,
        access_world.docs["beleg_original"],
        access_world.titles["beleg_original"],
    )


def test_d31_tenant_gets_released_version_with_redaction_note(
    access_client: TestClient, access_world: AccessWorld
) -> None:
    """D31, E06: the released version is visible for the tenant of the statement with the
    redaction note in list and download (no Vollverweigerung); the neighbour sees nothing."""
    released, original = access_world.docs["beleg_freigabe"], access_world.docs["beleg_original"]
    listed = {
        d["id"]: d for d in _ok(access_client.get(f"{P}/documents", headers=access_world.tenant_a))
    }
    assert set(listed) == {released}
    assert listed[released]["redaction_note"] == access.REDACTION_NOTE
    response = access_client.get(
        f"{P}/documents/{released}/download", headers=access_world.tenant_a
    )
    assert response.status_code == 200, response.text
    assert unquote(response.headers["X-Redaction-Note"]) == access.REDACTION_NOTE
    assert response.content == access_world.titles["beleg_freigabe"].encode()
    # Not a receipt of tenant B and not a GdWE document of owner 1.
    assert _portal_ids(access_client, access_world.tenant_b) == set()
    assert released not in _portal_ids(access_client, access_world.owner1)
    assert original not in _portal_ids(access_client, access_world.owner1)
    # The management still sees both, the link to the original is kept (role generated).
    out = _ok(access_client.get(f"/api/v1/documents/{released}", headers=access_world.admin))
    assert any(
        link["entity_type"] == "document" and link["entity_id"] == original for link in out["links"]
    )
