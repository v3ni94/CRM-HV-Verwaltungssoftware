"""M3-02 (portal stage), M21-02, M21-03: a SEPA mandate confirmed in the portal is a proposal
with Textform evidence (PDF, time stamp, IP) that never becomes active without a staff
decision and never creates a collecting mandate (G2); an address change is a proposal with a
date of validity and optional evidence that the staff decision writes into the contact with an
event; document visibility per role (internal, owner, tenant) and tenant separation."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _doc, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
IBAN = "DE89 3704 0044 0532 0130 00"
CREDITOR = "DE98ZZZ09999999999"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pm-a-{RUN}", name=f"Mandat A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pm-b-{RUN}", name=f"Mandat B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("pm_admin_a", a), ("pm_admin_b", b)):
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
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


@dataclass
class Setup:
    admin: dict[str, str]
    admin_b: dict[str, str]
    owner: dict[str, str]
    tenant: dict[str, str]
    owner_contact: str
    tenant_contact: str
    hoa: str
    ownership: dict[str, Any]
    tenancy: dict[str, Any]


def _build(c: TestClient, world: World) -> Setup:
    h = bearer(login(c, world, "pm_admin_a"))
    hb = bearer(login(c, world, "pm_admin_b"))
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "871", "name": "Mandat-WEG", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in weg["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, weg["id"], "01")
    owner_party, _ = _party(c, h, "MandatEig")
    ownership = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner_party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    rental = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "872", "name": "Mandat-Miethaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, "MandatVermieter", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit_r = _unit(c, h, rental["id"], "A")
    tenant_party, _ = _party(c, h, "MandatMieter")
    tenancy = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_r,
                "party_id": tenant_party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    owner_contact = _contact_of(c, h, owner_party)
    tenant_contact = _contact_of(c, h, tenant_party)
    return Setup(
        admin=h,
        admin_b=hb,
        owner=_portal_user(c, h, world, "pm_owner", owner_contact),
        tenant=_portal_user(c, h, world, "pm_tenant", tenant_contact),
        owner_contact=owner_contact,
        tenant_contact=tenant_contact,
        hoa=hoa,
        ownership=ownership,
        tenancy=tenancy,
    )


_SETUP: dict[str, Setup] = {}


def _setup(c: TestClient, world: World) -> Setup:
    if "s" not in _SETUP:
        _SETUP["s"] = _build(c, world)
    return _SETUP["s"]


def _rows(database: Database, tenant: Any, sql: str, **params: Any) -> list[Any]:
    """Read rows as the migrator with the tenant bound (RLS is forced for every role)."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant)},
            )
            return list(conn.execute(text(sql), params).all())
    finally:
        engine.dispose()


def test_mandate_requires_creditor_id_and_confirmation(
    client: TestClient, world: World, database: Database
) -> None:
    s = _setup(client, world)
    contract = s.ownership["id"]
    # No creditor identifier on the legal entity yet: no mandate text, no proposal.
    r = client.get(f"{P}/sepa-mandates/preview", params={"contract_id": contract}, headers=s.owner)
    assert r.status_code == 422, r.text
    _ok(
        client.put(
            f"/api/v1/accounting/direct-debits/creditor-ids/legal-entities/{s.hoa}",
            json={"sepa_creditor_id": CREDITOR},
            headers=s.admin,
        )
    )
    preview = _ok(
        client.get(f"{P}/sepa-mandates/preview", params={"contract_id": contract}, headers=s.owner)
    )
    assert preview["creditor_id"] == CREDITOR
    assert preview["sequence"] == "recurrent"
    assert "Gläubiger-Identifikationsnummer: " + CREDITOR in preview["text"]
    assert "wiederkehrende Zahlung" in preview["text"]
    assert len(preview["reference"]) <= 35
    # The tenant of the other property may not read the owner's contract.
    assert (
        client.get(
            f"{P}/sepa-mandates/preview", params={"contract_id": contract}, headers=s.tenant
        ).status_code
        == 404
    )
    body = {"contract_id": contract, "iban": IBAN, "holder": "Erika Eigentum", "confirmed": True}
    assert (
        client.post(
            f"{P}/sepa-mandates", json={**body, "confirmed": False}, headers=s.owner
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{P}/sepa-mandates", json={**body, "iban": "DE00 1234"}, headers=s.owner
        ).status_code
        == 422
    )
    assert client.post(f"{P}/sepa-mandates", json=body, headers=s.tenant).status_code == 404


def test_mandate_is_a_proposal_until_staff_decides(
    client: TestClient, world: World, database: Database
) -> None:
    s = _setup(client, world)
    contract = s.ownership["id"]
    _ok(
        client.put(
            f"/api/v1/accounting/direct-debits/creditor-ids/legal-entities/{s.hoa}",
            json={"sepa_creditor_id": CREDITOR},
            headers=s.admin,
        )
    )
    body = {"contract_id": contract, "iban": IBAN, "holder": "Erika Eigentum", "confirmed": True}
    proposal = _ok(client.post(f"{P}/sepa-mandates", json=body, headers=s.owner), 201)
    assert proposal["status"] == "proposed"
    assert proposal["iban_masked"] == "DE89 **** **** 3000"
    assert proposal["confirmed_at"]
    # Textform evidence: PDF visible to the account holder, carries text, time stamp and IP.
    pdf = client.get(f"{P}/documents/{proposal['evidence_document_id']}/download", headers=s.owner)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    stored = _rows(
        database,
        world.tenant_a,
        "SELECT confirmed_ip, mandate_text, status FROM portal_sepa_mandate_proposal WHERE id = :id",
        id=proposal["id"],
    )[0]
    assert stored[0]
    assert "Mandatsreferenz: " + proposal["reference"] in stored[1]
    # Nothing active: no contact bank account, no collecting mandate (G2).
    assert (
        _ok(client.get(f"/api/v1/contacts/{s.owner_contact}/sepa-mandates", headers=s.admin)) == []
    )
    assert (
        _rows(
            database,
            world.tenant_a,
            "SELECT count(*) FROM sepa_mandate WHERE tenant_id = :t",
            t=str(world.tenant_a),
        )[0][0]
        == 0
    )
    mine = _ok(client.get(f"{P}/sepa-mandates", headers=s.owner))
    assert [m["id"] for m in mine] == [proposal["id"]]
    assert _ok(client.get(f"{P}/sepa-mandates", headers=s.tenant)) == []
    # Portal users cannot decide; the other tenant does not see the proposal at all.
    assert (
        client.post(
            f"{PA}/sepa-mandate-proposals/{proposal['id']}/decide",
            json={"accept": True},
            headers=s.owner,
        ).status_code
        == 403
    )
    assert _ok(client.get(f"{PA}/sepa-mandate-proposals", headers=s.admin_b)) == []
    assert (
        client.post(
            f"{PA}/sepa-mandate-proposals/{proposal['id']}/decide",
            json={"accept": True},
            headers=s.admin_b,
        ).status_code
        == 404
    )
    queue = _ok(
        client.get(f"{PA}/sepa-mandate-proposals", params={"status": "proposed"}, headers=s.admin)
    )
    assert [q["id"] for q in queue] == [proposal["id"]]
    decided = _ok(
        client.post(
            f"{PA}/sepa-mandate-proposals/{proposal['id']}/decide",
            json={"accept": True, "note": "geprüft"},
            headers=s.admin,
        )
    )
    assert decided["status"] == "accepted"
    assert decided["contact_bank_account_id"]
    # Acceptance records the evidence on a contact bank account that still awaits the four
    # eyes release of the IBAN; still no collecting mandate.
    mandates = _ok(client.get(f"/api/v1/contacts/{s.owner_contact}/sepa-mandates", headers=s.admin))
    assert [m["mandate_reference"] for m in mandates] == [proposal["reference"]]
    assert mandates[0]["mandate_status"] == "active"
    approval, granted_via = _rows(
        database,
        world.tenant_a,
        "SELECT approval_status, mandate_granted_via FROM contact_bank_account WHERE id = :id",
        id=decided["contact_bank_account_id"],
    )[0]
    assert approval == "pending"
    assert granted_via == "portal"
    assert (
        _rows(
            database,
            world.tenant_a,
            "SELECT count(*) FROM sepa_mandate WHERE tenant_id = :t",
            t=str(world.tenant_a),
        )[0][0]
        == 0
    )
    assert (
        client.post(
            f"{PA}/sepa-mandate-proposals/{proposal['id']}/decide",
            json={"accept": False},
            headers=s.admin,
        ).status_code
        == 409
    )
    events = _rows(
        database,
        world.tenant_a,
        "SELECT type FROM domain_event WHERE entity_id = :id ORDER BY occurred_at",
        id=proposal["id"],
    )
    assert [e[0] for e in events] == [
        "portal.sepa_mandate.proposed",
        "portal.sepa_mandate.accepted",
    ]


def test_address_change_with_validity_and_evidence(
    client: TestClient, world: World, database: Database
) -> None:
    s = _setup(client, world)
    base = {
        "street": "Neue Straße",
        "house_number": "5",
        "postal_code": "40213",
        "city": "Düsseldorf",
    }
    # Date of validity is required; a foreign document is refused as evidence.
    assert (
        client.post(
            f"{P}/change-requests", json={"kind": "address", "payload": base}, headers=s.tenant
        ).status_code
        == 422
    )
    foreign = _doc(client, s.admin, "Fremd", "contract", s.ownership["id"], ["owner"])
    assert (
        client.post(
            f"{P}/change-requests",
            json={
                "kind": "address",
                "payload": {**base, "valid_from": "2026-09-01", "document_id": foreign},
            },
            headers=s.tenant,
        ).status_code
        == 422
    )
    upload = _ok(
        client.post(
            f"{P}/uploads",
            files={"file": ("melde.pdf", b"%PDF-1.4\n%evidence\n", "application/pdf")},
            headers=s.tenant,
        ),
        201,
    )
    proposal = _ok(
        client.post(
            f"{P}/change-requests",
            json={
                "kind": "address",
                "payload": {**base, "valid_from": "2026-09-01", "document_id": upload["id"]},
            },
            headers=s.tenant,
        ),
        201,
    )
    before = _ok(client.get(f"/api/v1/contacts/{s.tenant_contact}", headers=s.admin))["addresses"]
    assert all(a["street"] != "Neue Straße" for a in before)
    _ok(
        client.post(
            f"{PA}/change-requests/{proposal['id']}/decide", json={"accept": True}, headers=s.admin
        )
    )
    after = _ok(client.get(f"/api/v1/contacts/{s.tenant_contact}", headers=s.admin))["addresses"]
    new = [a for a in after if a["street"] == "Neue Straße"]
    assert len(new) == 1
    assert new[0]["is_primary"] is True
    assert new[0]["postal_code"] == "40213"
    assert sum(1 for a in after if a["is_primary"]) == 1
    events = _rows(
        database,
        world.tenant_a,
        "SELECT payload FROM domain_event WHERE type = 'contact.address_changed' "
        "AND entity_id = :id",
        id=s.tenant_contact,
    )
    assert len(events) == 1
    assert events[0][0]["valid_from"] == "2026-09-01"
    assert events[0][0]["evidence_document_id"] == upload["id"]
    # A future date: stored, not yet primary.
    later = _ok(
        client.post(
            f"{P}/change-requests",
            json={
                "kind": "address",
                "payload": {**base, "street": "Später", "valid_from": "2099-01-01"},
            },
            headers=s.tenant,
        ),
        201,
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{later['id']}/decide", json={"accept": True}, headers=s.admin
        )
    )
    after = _ok(client.get(f"/api/v1/contacts/{s.tenant_contact}", headers=s.admin))["addresses"]
    assert next(a for a in after if a["street"] == "Später")["is_primary"] is False
    assert next(a for a in after if a["street"] == "Neue Straße")["is_primary"] is True


def test_visibility_per_role_internal_owner_tenant(client: TestClient, world: World) -> None:
    s = _setup(client, world)
    internal = _doc(client, s.admin, "Intern", "legal_entity", s.hoa, ["internal"])
    for_owner = _doc(client, s.admin, "Beschluss", "legal_entity", s.hoa, ["owner"])
    for_tenant_only = _doc(client, s.admin, "Hausordnung", "legal_entity", s.hoa, ["tenant"])
    tenancy_doc = _doc(client, s.admin, "Mietvertrag", "contract", s.tenancy["id"], ["tenant"])
    tenancy_internal = _doc(client, s.admin, "Bonität", "contract", s.tenancy["id"], ["internal"])
    assert (
        client.patch(
            f"/api/v1/documents/{internal}", json={"visibility": []}, headers=s.admin
        ).status_code
        == 422
    )
    owner_docs = {d["id"] for d in _ok(client.get(f"{P}/documents", headers=s.owner))}
    tenant_docs = {d["id"] for d in _ok(client.get(f"{P}/documents", headers=s.tenant))}
    assert for_owner in owner_docs
    assert not {internal, for_tenant_only, tenancy_doc, tenancy_internal} & owner_docs
    assert tenancy_doc in tenant_docs
    assert not {internal, for_owner, for_tenant_only, tenancy_internal} & tenant_docs
    for doc in (internal, tenancy_internal):
        assert client.get(f"{P}/documents/{doc}/download", headers=s.owner).status_code == 404
        assert client.get(f"{P}/documents/{doc}/download", headers=s.tenant).status_code == 404
    # CRM view of the flag: "internal" is an explicit choice, listed on the document.
    detail = _ok(client.get(f"/api/v1/documents/{internal}", headers=s.admin))
    assert detail["visibility"] == ["internal"]
