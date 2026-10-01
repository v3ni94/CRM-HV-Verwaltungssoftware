"""T13 (SD-05, SD-06, SD-07): acceptance cases PUE12, W13 and PUE13 against existing functions.

Expected values by hand (synthetic): an invitation is valid 14 days (INVITE_DAYS); an expired
invitation cannot be accepted (422); documents of an ended tenancy are no longer visible; the
default document order is newest first, ``title_asc`` gives Alpha before Zeta; a bundle of two
documents holds three files (two documents and INDEX.csv); a package has exactly the events
status, status, package, note, note, status, notified, retrieval; neither a board audit nor its
confirmation changes a resolution (W13), and an audit needs no board account."""

import asyncio
import io
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _doc, _ok, _portal_user
from tests.integration.test_m21_read_receipts import _db
from tests.integration.test_q10_portal_w3 import _tenant_setup

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
H = "/api/v1/hoa"


async def _world_t13(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services
    from tests.integration.test_m2_platform import RUN

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t13a-{RUN}", name=f"T13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t13b-{RUN}", name=f"T13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("t13admin", a), ("t13adminb", b)):
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
    # Own tenants and users: the q10 world builder cannot run twice in one process (slugs
    # and e-mail addresses derive from the constant RUN).
    return asyncio.run(_world_t13(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def test_sd05_pue12_invitation_scope_search_sort_bundle(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    ha = bearer(login(client, world, "t13admin"))
    contract, meta = _tenant_setup(client, ha, world, "931")
    d_zeta = _doc(client, ha, "Zeta Beleg", "contract", contract, ["tenant"])
    d_alpha = _doc(client, ha, "Alpha Beleg", "contract", contract, ["tenant"])
    d_owner = _doc(client, ha, "Nur Eigentuemer", "contract", contract, ["owner"])
    contact = _contact_of(client, ha, meta["party"])

    # Time limited invitation: the account is "invited", expiry within INVITE_DAYS (14 days).
    _, guest = _party(client, ha, "T13Gast")
    guest_contact = str(guest["id"])
    inv = _ok(
        client.post(
            f"{PA}/accounts",
            json={
                "contact_id": guest_contact,
                "email": world.email("t13guest"),
                "display_name": "t13g",
            },
            headers=ha,
        ),
        201,
    )
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": guest_contact}, headers=ha))[0]
    assert row["status"] == "invited"
    expires = datetime.fromisoformat(row["invitation_expires_at"])
    assert timedelta(days=13) < expires - datetime.now(UTC) <= timedelta(days=14, minutes=5)

    async def expire(s: Any) -> None:
        await s.execute(
            text("UPDATE portal_account SET invitation_expires_at = :at WHERE contact_id = :c"),
            {"at": datetime.now(UTC) - timedelta(days=1), "c": uuid.UUID(guest_contact)},
        )

    _db(database, redis_url, world, expire)
    expired = client.post(
        f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
    )
    assert expired.status_code == 422, "an expired invitation must not open access"
    # T13-01: an expired, never accepted invitation is issued again (new token, expiry reset);
    # the old token stays unusable, the account is not duplicated.
    body = {"contact_id": guest_contact, "email": world.email("t13guest"), "display_name": "t13g"}
    again = _ok(client.post(f"{PA}/accounts", json=body, headers=ha), 201)
    assert again["id"] == inv["id"]
    assert again["invitation_token"] != inv["invitation_token"]
    rows = _ok(client.get(f"{PA}/accounts", params={"contact_id": guest_contact}, headers=ha))
    assert len(rows) == 1
    assert rows[0]["status"] == "invited"
    renewed = datetime.fromisoformat(rows[0]["invitation_expires_at"])
    assert timedelta(days=13) < renewed - datetime.now(UTC) <= timedelta(days=14, minutes=5)
    assert (
        client.post(
            f"{P}/invitations/accept",
            json={"token": inv["invitation_token"], "password": PASSWORD},
        ).status_code
        == 422
    )
    # A still valid invitation is no reason for a second one (409).
    assert client.post(f"{PA}/accounts", json=body, headers=ha).status_code == 409
    accepted = client.post(
        f"{P}/invitations/accept",
        json={"token": again["invitation_token"], "password": PASSWORD},
    )
    assert accepted.status_code < 300, accepted.text
    # An active account is never invited again (409), also not after the expiry date.
    _db(database, redis_url, world, expire)
    assert client.post(f"{PA}/accounts", json=body, headers=ha).status_code == 409
    portal = _portal_user(client, ha, world, "t13res", contact)

    # Read rights and scope: only the tenant release; the owner only document stays hidden.
    listed = _ok(client.get(f"{P}/documents", headers=portal))
    assert {d["id"] for d in listed} == {d_zeta, d_alpha}
    assert d_owner not in {d["id"] for d in listed}
    assert client.get(f"{P}/documents/{d_owner}", headers=portal).status_code == 404
    assert client.get(f"{P}/documents/{d_owner}/download", headers=portal).status_code == 404
    # Writing is not part of the portal documents (no PUT, PATCH, DELETE route).
    assert client.delete(f"{P}/documents/{d_alpha}", headers=portal).status_code in (404, 405)
    assert client.patch(f"{P}/documents/{d_alpha}", json={}, headers=portal).status_code in (
        404,
        405,
    )

    # Search and sorted list (only inside the visible set).
    titles = lambda q: [d["title"] for d in _ok(client.get(f"{P}/documents?{q}", headers=portal))]  # noqa: E731
    assert titles("sort=title_asc") == ["Alpha Beleg", "Zeta Beleg"]
    assert titles("sort=title_desc") == ["Zeta Beleg", "Alpha Beleg"]
    assert titles("sort=created_asc") == ["Zeta Beleg", "Alpha Beleg"]  # created Zeta, then Alpha
    assert titles("") == ["Alpha Beleg", "Zeta Beleg"]  # default: newest first
    assert titles("q=zeta") == ["Zeta Beleg"]
    assert titles("q=Eigentuemer") == []  # search never reaches hidden documents
    assert client.get(f"{P}/documents?q={'x' * 101}", headers=portal).status_code == 422

    # Single and bundle download within the scope; foreign id answers 404 for the whole bundle.
    one = client.get(f"{P}/documents/{d_zeta}/download", headers=portal)
    assert one.status_code == 200
    assert one.content == b"Zeta Beleg"
    bundle = client.post(
        f"{P}/documents/bundle", json={"document_ids": [d_zeta, d_alpha]}, headers=portal
    )
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert len(archive.namelist()) == 3
        assert "INDEX.csv" in archive.namelist()
    assert (
        client.post(
            f"{P}/documents/bundle", json={"document_ids": [d_zeta, d_owner]}, headers=portal
        ).status_code
        == 404
    )

    # An ended tenancy grants nothing: a second tenant with a contract ended in 2023.
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "932", "name": "T13 Haus 932", "management_type": "rental"},
            headers=ha,
        ),
        201,
    )
    landlord, _ = _party(client, ha, "T13Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=ha,
        ),
        201,
    )
    unit = _unit(client, ha, prop["id"], "A")
    old_party, _ = _party(client, ha, "T13Altmieter")
    old = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": old_party,
                "start_date": "2022-01-01",
                "end_date": "2023-12-31",
            },
            headers=ha,
        ),
        201,
    )
    d_old = _doc(client, ha, "Altbeleg", "contract", str(old["id"]), ["tenant"])
    old_portal = _portal_user(client, ha, world, "t13old", _contact_of(client, ha, old_party))
    assert d_old not in {d["id"] for d in _ok(client.get(f"{P}/documents", headers=old_portal))}
    assert client.get(f"{P}/documents/{d_old}/download", headers=old_portal).status_code == 404

    # Portal role without staff right: no CRM audit access (permission frame).
    assert client.get(f"{H}/inspection-requests", headers=portal).status_code == 403


def _hoa_with_owner(client: TestClient, h: dict[str, str], number: str) -> tuple[str, str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"WEG T13 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    party, contact = _party(client, h, f"T13Eig{number}")
    unit = _unit(client, h, prop["id"], "01")
    contract = _ok(
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
    return hoa, str(contract["id"]), str(contact["id"])


def test_sd06_w13_board_review_is_no_resolution_and_needs_no_board(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "t13admin"))
    hoa, owner_contract, auditor = _hoa_with_owner(client, h, "933")
    base = {"legal_entity_id": hoa, "scheduled_at": "2026-06-20T10:00:00+02:00"}
    meeting = _ok(client.post(f"{H}/meetings", json=base, headers=h), 201)
    item = _ok(
        client.post(
            f"{H}/meetings/{meeting['id']}/agenda",
            json={"title": "Genehmigung Jahresabrechnung", "subject_type": "hoa_statement"},
            headers=h,
        ),
        201,
    )

    # No board account exists: an audit is still possible, and the board section stays empty.
    eng = _ok(
        client.post(
            f"{H}/audits",
            json={
                "legal_entity_id": hoa,
                "period_from": "2025-01-01",
                "period_to": "2025-12-31",
                "purpose": "Vorpruefung W13",
                "auditor_contact_ids": [auditor],
            },
            headers=h,
        ),
        201,
    )["id"]
    board = _ok(client.get(f"{H}/audit-engagements/{eng}/board", headers=h))
    assert board["access"] == [], "no board account is invented"

    # Review report and confirmation: no entry in the resolution collection, audit stays open.
    report = _ok(
        client.post(f"{H}/audits/{eng}/reports", json={"findings": "Stichprobe ok"}, headers=h),
        201,
    )
    _ok(
        client.post(
            f"{H}/audits/{eng}/reports/{report['version']}/confirm",
            json={"confirmed_by_name": "Beirat Muster", "note": "Kenntnis genommen"},
            headers=h,
        )
    )
    assert _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h)) == []
    assert _ok(client.get(f"{H}/audits/{eng}", headers=h))["status"] == "open"

    # The decision itself stays a separate act: voting and announcing create the resolution.
    mid = meeting["id"]
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-05-29"}, headers=h))
    _ok(
        client.post(
            f"{H}/meetings/{mid}/attendance",
            json={"contract_id": owner_contract, "present": True},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/agenda/{item['id']}/votes",
            json={"contract_id": owner_contract, "choice": "yes"},
            headers=h,
        ),
        201,
    )
    tally = _ok(client.get(f"{H}/agenda/{item['id']}/tally", headers=h))
    assert tally["proposal"] == "positive"
    assert _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h)) == []
    res = _ok(
        client.post(
            f"{H}/agenda/{item['id']}/announce",
            json={"outcome": "positive", "majority_basis": "einfache Mehrheit"},
            headers=h,
        ),
        201,
    )
    assert res["status"] == "positive"
    # Finding (reported, not asserted as feature): the agenda item carries no reference to an
    # audit and announcing is not blocked by a missing review (W13: provision is open).
    listed = _ok(client.get(f"{H}/resolutions", params={"legal_entity_id": hoa}, headers=h))
    assert len(listed) == 1
    assert _ok(client.get(f"{H}/audits/{eng}", headers=h))["status"] == "open"


def test_sd07_pue13_protocol_without_legal_fiction(client: TestClient, world: World) -> None:
    """Full course on the existing functions; complements the P08 case SD-07."""
    from tests.integration.test_p08_hoa_audit_inspection import INS, _released_request

    h = bearer(login(client, world, "t13admin"))
    _, rid, d1, _ = _released_request(client, h, "934")
    _ok(
        client.post(
            f"{INS}/{rid}/package", json={"document_ids": [d1], "valid_days": 14}, headers=h
        )
    )
    _ok(client.post(f"{INS}/{rid}/notes", json={"text": "Rückfrage zu Position 3"}, headers=h), 201)
    _ok(client.post(f"{INS}/{rid}/notes", json={"text": "Antwort der Verwaltung"}, headers=h), 201)
    _ok(
        client.post(
            f"{INS}/{rid}/transition",
            json={"status": "provided", "delivery_kind": "portal"},
            headers=h,
        )
    )
    assert client.get(f"{INS}/{rid}/package", headers=h).status_code == 200
    detail = _ok(client.get(f"{INS}/{rid}", headers=h))
    kinds = [e["kind"] for e in detail["events"]]
    assert kinds == [
        "status",
        "status",
        "package",
        "note",
        "note",
        "status",
        "notified",
        "retrieval",
    ]
    # Retrieval is recorded as retrieval (status retrieved for hoa:update): no acknowledgement,
    # no acceptance, no waiver.
    assert detail["status"] in ("provided", "retrieved")
    forbidden = {"acknowledged", "accepted", "waived", "approved"}
    assert not [e for e in detail["events"] if e.get("to_status") in forbidden]
    # A transition to an acceptance like status is refused (422 or 409), the status is unchanged.
    for bad in ("acknowledged", "accepted"):
        assert client.post(
            f"{INS}/{rid}/transition", json={"status": bad}, headers=h
        ).status_code in (409, 422)
    assert _ok(client.get(f"{INS}/{rid}", headers=h))["status"] == detail["status"]
    # Old link: after revocation no retrieval (no lasting inspection from an old release).
    _ok(client.post(f"{INS}/{rid}/revoke", json={"text": "Eigentümerwechsel"}, headers=h))
    assert client.get(f"{INS}/{rid}/package", headers=h).status_code == 409
