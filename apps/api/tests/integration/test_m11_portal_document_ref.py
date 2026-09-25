"""M11-finapi Stage 4: `GET /api/v1/portal/account` rows carry a `document_id` only when the
booking behind that open item (`JournalEntry.document_id`) is a document this portal account
may actually see (same check `GET /portal/documents/{id}/download` re-runs); scoped strictly to
the caller's own contract, never another owner's or tenant's."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pd-{RUN}", name=f"PortalDoc {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("pdadmin"), display_name="admin", password=PASSWORD
        )
        world.users["pdadmin"] = uid
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
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return bearer(login(c, world, name))


def _contact_of(c: TestClient, h: dict[str, str], party: str) -> str:
    return str(_ok(c.get(f"/api/v1/parties/{party}", headers=h))["members"][0]["contact_id"])


def test_account_statement_carries_document_ref_within_own_scope(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "pdadmin"))
    rental = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "911", "name": "Belegweg", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, "Vermieter", "company")
    owner = _ok(
        client.post(
            f"/api/v1/properties/{rental['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    legal_entity = owner["legal_entity_id"]
    unit_a = _unit(client, h, rental["id"], "A")
    unit_b = _unit(client, h, rental["id"], "B")
    party_a, _ = _party(client, h, "MieterA")
    party_b, _ = _party(client, h, "MieterB")
    tenant_a_contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_a,
                "party_id": party_a,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    tenant_b_contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_b,
                "party_id": party_b,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )

    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": legal_entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    _ok(client.post(f"{A}/ledgers/{ledger}/sync-debtors", headers=h))
    all_accounts = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    debtor_a = next(a["id"] for a in all_accounts if a["party_id"] == party_a)
    # A balanced counter line only; the debtor category on this side (credit > debit) never
    # creates its own open item, so this stays a clean single-row fixture for the test.
    counter_account = next(a["id"] for a in all_accounts if a["party_id"] == party_b)

    # A document (the rent charge notice) attached to tenant A's contract, released for
    # "tenant"; the booking that creates the open item carries it as `document_id`.
    charge_doc = _doc(
        client, h, "Mietvorschreibung", "contract", tenant_a_contract["id"], ["tenant"]
    )

    entry = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries",
            json={
                "booking_date": "2026-03-01",
                "due_date": "2026-03-03",
                "text": "Miete März",
                "kind": "receivable",
                "document_id": charge_doc,
                "contract_id": tenant_a_contract["id"],
                "lines": [
                    {"account_id": debtor_a, "debit": "650.00", "credit": "0.00"},
                    {"account_id": counter_account, "debit": "0.00", "credit": "650.00"},
                ],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{entry['id']}/post", headers=h))

    ta = _portal_user(
        client, h, world, "pd-tenantA", _contact_of(client, h, tenant_a_contract["party_id"])
    )
    tb = _portal_user(
        client, h, world, "pd-tenantB", _contact_of(client, h, tenant_b_contract["party_id"])
    )

    statement_a = _ok(client.get(f"{P}/account", headers=ta))
    assert len(statement_a["items"]) == 1
    assert statement_a["items"][0]["document_id"] == charge_doc
    # Own scope only: tenant B has no open items and never sees tenant A's reference.
    statement_b = _ok(client.get(f"{P}/account", headers=tb))
    assert statement_b["items"] == []

    # Same document, but not released for the tenant role: no reference is exposed even
    # though the booking still carries the document at the accounting level (rule 0.1.3: a
    # portal row is never a bare id the download endpoint would then refuse).
    _ok(
        client.patch(
            f"/api/v1/documents/{charge_doc}",
            json={"visibility": ["owner"]},
            headers=h,
        )
    )
    statement_a_after = _ok(client.get(f"{P}/account", headers=ta))
    assert statement_a_after["items"][0]["document_id"] is None
