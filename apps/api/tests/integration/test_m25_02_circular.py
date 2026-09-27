"""M25-02 circular resolution with a lowered majority. Expected values by hand:
owner A holds units 01 and 02 (MEA 400 + 300), owner B unit 03 (MEA 300).
Head: A yes (counted once), B no -> 1 : 1 -> negative, eligible 2.
MEA (tenant rule for the subject kind): 700 : 300 -> positive.
A vote received after the deadline is not counted (late) and counts as missing for unanimity.
Without the tenant switch (default off) or without a positive prior admitting resolution of
the same community the simple majority is refused; a resolution of another tenant is invisible
(RLS) and therefore refused as well."""

import asyncio
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
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cr25a-{RUN}", name=f"CRA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cr25b-{RUN}", name=f"CRB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("cr25a", a), ("cr25b", b)):
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


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _community(client: TestClient, h: dict[str, str], number: str) -> tuple[str, dict[str, str]]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG Umlauf {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    party_a, _ = _party(client, h, "UmlaufA")
    party_b, _ = _party(client, h, "UmlaufB")
    contracts: dict[str, str] = {}
    for no, mea, party in [("01", "400", party_a), ("02", "300", party_a), ("03", "300", party_b)]:
        unit = _unit(client, h, prop["id"], no)
        _ok(
            client.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": keys["MEA"], "value": mea, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        contracts[no] = _ok(
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
        )["id"]
    return hoa, contracts


def _enabling(client: TestClient, h: dict[str, str], hoa: str, status: str = "positive") -> str:
    return str(
        _ok(
            client.post(
                f"{H}/resolutions",
                json={
                    "legal_entity_id": hoa,
                    "decided_on": "2026-05-10",
                    "subject": "Absenkung für die Hausordnung",
                    "wording": "Für die Änderung der Hausordnung genügt im Umlaufverfahren die "
                    "Mehrheit der abgegebenen Stimmen.",
                    "status": status,
                    "kind": "meeting",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_circular_lower_majority(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cr25a"))
    hoa, contracts = _community(client, h, "771")
    evidence = _doc(client, h, "umlauf.pdf")
    base = {
        "legal_entity_id": hoa,
        "subject": "Hausordnung",
        "wording": "Die Hausordnung wird angepasst.",
        "decided_on": "2026-07-01",
        "evidence_document_id": evidence,
        "allowed_majority": "simple",
        "subject_kind": "other",
        "vote_deadline_at": "2026-06-30T23:59:59+02:00",
    }
    votes = {
        contracts["01"]: {
            "choice": "yes",
            "channel": "email",
            "received_at": "2026-06-20T10:00:00Z",
        },
        contracts["02"]: {
            "choice": "yes",
            "channel": "portal",
            "received_at": "2026-06-21T10:00:00Z",
        },
        contracts["03"]: {
            "choice": "no",
            "channel": "email",
            "received_at": "2026-06-22T10:00:00Z",
        },
    }

    # Switch off (default): refused for the tenant, switch state readable.
    assert _ok(client.get(f"{H}/circular-lower-majority", headers=h)) == {"enabled": False}
    refused = client.post(f"{H}/circular-resolutions", json=base | {"consents": votes}, headers=h)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-HOA-0001"
    _ok(client.put(f"{H}/circular-lower-majority", json={"enabled": True}, headers=h))

    # Switch on, but no admitting resolution: refused. Negative or later resolutions as well.
    refused = client.post(f"{H}/circular-resolutions", json=base | {"consents": votes}, headers=h)
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "MHVP-HOA-0002"
    negative = _enabling(client, h, hoa, status="negative")
    assert (
        client.post(
            f"{H}/circular-resolutions",
            json=base | {"consents": votes, "enabling_resolution_id": negative},
            headers=h,
        ).status_code
        == 422
    )
    enabling = _enabling(client, h, hoa)
    late_basis = base | {"consents": votes, "enabling_resolution_id": enabling}
    assert (
        client.post(
            f"{H}/circular-resolutions", json=late_basis | {"decided_on": "2026-05-01"}, headers=h
        ).status_code
        == 422
    )
    # deadline and subject kind are mandatory for the simple majority
    assert (
        client.post(
            f"{H}/circular-resolutions", json=late_basis | {"vote_deadline_at": None}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{H}/circular-resolutions", json=late_basis | {"subject_kind": None}, headers=h
        ).status_code
        == 422
    )

    # Head count (default rule): A once yes, B no -> 1 : 1 -> negative.
    head = _ok(client.post(f"{H}/circular-resolutions", json=late_basis, headers=h), 201)
    assert head["status"] == "negative"
    assert (head["tally"]["principle"], head["tally"]["yes"], head["tally"]["no"]) == (
        "head",
        "1",
        "1",
    )
    assert head["tally"]["eligible"] == "2"
    assert head["majority_check"]["result"] == "nicht erreicht"
    assert "zulassendem Beschluss Nr." in head["majority_basis"]
    assert "zu prüfen" in head["majority_basis"]

    # Tenant rule by MEA for the subject kind: 700 : 300 -> positive.
    _ok(
        client.post(
            f"{H}/majority-rules/subject-rules",
            json={
                "subject_kind": "other",
                "majority_type": "simple",
                "counting_basis": "shares",
                "source": "Gemeinschaftsordnung § 7 (Testannahme)",
                "legal_entity_id": hoa,
            },
            headers=h,
        ),
        201,
    )
    mea = _ok(client.post(f"{H}/circular-resolutions", json=late_basis, headers=h), 201)
    assert mea["status"] == "positive"
    assert (mea["tally"]["principle"], mea["tally"]["yes"], mea["tally"]["no"]) == (
        "mea",
        "700",
        "300",
    )
    assert mea["majority_check"]["result"] == "erreicht"

    # A vote after the deadline is not counted: only A's 700 remain, B is late -> positive,
    # late = 1; the same vote makes the unanimous variant negative (missing).
    late_votes = dict(votes) | {
        contracts["03"]: {"choice": "no", "channel": "email", "received_at": "2026-07-01T08:00:00Z"}
    }
    late = _ok(
        client.post(
            f"{H}/circular-resolutions", json=late_basis | {"consents": late_votes}, headers=h
        ),
        201,
    )
    assert (late["status"], late["late"], late["tally"]["no"]) == ("positive", 1, "0")
    unanimous = _ok(
        client.post(
            f"{H}/circular-resolutions",
            json=base
            | {
                "allowed_majority": "unanimous",
                "consents": dict.fromkeys(contracts.values(), "yes")
                | {contracts["03"]: {"choice": "yes", "received_at": "2026-07-01T08:00:00Z"}},
            },
            headers=h,
        ),
        201,
    )
    assert (unanimous["status"], unanimous["missing"]) == ("negative", 1)

    # Collection carries the new fields; the portal summary reads the weighted tally.
    listed = _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    row = next(r for r in listed if r["id"] == mea["id"])
    assert row["allowed_majority"] == "simple"
    assert row["enabling_resolution_id"] == enabling
    assert row["vote_deadline_at"] is not None
    assert row["votes"]["protocol"]["result"] == "positive"
    assert row["votes"]["consents"][contracts["02"]]["channel"] == "portal"

    # Tenant separation: tenant B (switch on) cannot use tenant A's admitting resolution.
    hb = bearer(login(client, world, "cr25b", tenant_id=world.tenant_b))
    hoa_b, contracts_b = _community(client, hb, "772")
    evidence_b = _doc(client, hb, "umlauf-b.pdf")
    _ok(client.put(f"{H}/circular-lower-majority", json={"enabled": True}, headers=hb))
    foreign = client.post(
        f"{H}/circular-resolutions",
        json=base
        | {
            "legal_entity_id": hoa_b,
            "evidence_document_id": evidence_b,
            "enabling_resolution_id": enabling,
            "consents": dict.fromkeys(contracts_b.values(), "yes"),
        },
        headers=hb,
    )
    assert foreign.status_code == 422, foreign.text
    assert foreign.json()["code"] == "MHVP-HOA-0002"
    # the switch of tenant B does not open tenant A's circular resolutions once A is off again
    _ok(client.put(f"{H}/circular-lower-majority", json={"enabled": False}, headers=h))
    assert client.post(f"{H}/circular-resolutions", json=late_basis, headers=h).status_code == 403
