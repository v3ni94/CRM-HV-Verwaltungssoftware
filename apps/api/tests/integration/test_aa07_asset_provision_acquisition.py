"""AA07: asset report in the owner portal with provision log per owner (GA07-02) and four eyes
release of special acquisitions in the statement package (GA07-03).

Expected values (hand derived): an asset report of an empty ledger reconciles (all sums 0,00)
and can be issued. The owner portal user of the unit sees the issued report, the PDF call writes
one provision row for the ownership contract; the CRM log then shows one retrieval for unit 01.
Unit 02 has an ownership contract that starts 01.03.2026 by inheritance: the statement package
of 2026 carries the finding ``acquisition_unreleased`` until a first person requested and a
different second person released it. Purchase contracts cause no finding.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal_owner import _contact_of, _ok, _portal_user
from tests.integration.test_m24_hoa import _hoa_ledger

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"


class OpenG4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G4


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa07a-{RUN}", name=f"AA07 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa07b-{RUN}", name=f"AA07 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aa07first", a, "tenant_admin"),
            ("aa07second", a, "tenant_admin"),
            ("aa07reader", a, "read_only"),
            ("aa07other", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
        ):
            yield closed, open_


def _ownership(
    c: TestClient, h: dict[str, str], unit: str, party: str, start: str, kind: str, **extra: Any
) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": start,
                "title_transfer_date": start,
                "acquisition_kind": kind,
                **extra,
            },
            headers=h,
        ),
        201,
    )


def test_asset_report_portal_and_provision_log(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, gated = clients
    h = bearer(login(closed, world, "aa07first"))
    hr = bearer(login(closed, world, "aa07reader"))
    ho = bearer(login(closed, world, "aa07other"))
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    w = _hoa_ledger(closed, h, "971")
    unit = _unit(closed, h, w["property"], "01")
    party, _ = _party(closed, h, "AA07Eigentuemer")
    contract = _ownership(closed, h, unit, party, "2020-01-01", "purchase")
    owner = _portal_user(closed, h, world, "aa07owner", _contact_of(closed, h, party))

    report = _ok(
        closed.post(
            f"{H}/asset-reports", json={"ledger_id": w["ledger"], "as_of": "2025-12-31"}, headers=h
        ),
        201,
    )
    rid = report["id"]
    # draft is invisible for the owner
    assert _ok(closed.get(f"{P}/owner/asset-reports", headers=owner))["items"] == []
    assert closed.get(f"{P}/owner/asset-reports/{rid}/pdf", headers=owner).status_code in (403, 404)
    _ok(closed.post(f"{H}/asset-reports/{rid}/calculate", headers=h))
    _ok(gated.post(f"{H}/asset-reports/{rid}/transition", json={"target": "issued"}, headers=h))

    listed = _ok(closed.get(f"{P}/owner/asset-reports", headers=owner))["items"]
    assert [i["report_id"] for i in listed] == [rid]
    # gate G4 closed: no PDF; open: PDF and one provision row
    assert closed.get(f"{P}/owner/asset-reports/{rid}/pdf", headers=owner).status_code == 403
    res = gated.get(f"{P}/owner/asset-reports/{rid}/pdf", headers=owner)
    assert res.status_code == 200, res.text
    assert res.content.startswith(b"%PDF")

    log = _ok(closed.get(f"{H}/asset-reports/{rid}/provisions", headers=h))
    assert [(i["unit_number"], i["retrievals"]) for i in log["items"]] == [("01", 1)]
    assert log["items"][0]["contract_id"] == contract["id"]
    assert log["items"][0]["first_retrieved_at"]
    assert log["note"]
    # authorization and tenant separation
    assert closed.get(f"{H}/asset-reports/{rid}/provisions", headers=hr).status_code == 200
    assert closed.get(f"{H}/asset-reports/{rid}/provisions", headers=ho).status_code == 404
    assert closed.get(f"{P}/owner/asset-reports", headers=h).status_code in (401, 403)
    assert closed.get(f"{P}/owner/asset-reports/not-a-uuid/pdf", headers=owner).status_code == 422


def test_special_acquisition_blocks_package_until_second_person_releases(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    c, _ = clients
    h1 = bearer(login(c, world, "aa07first"))
    h2 = bearer(login(c, world, "aa07second"))
    hr = bearer(login(c, world, "aa07reader"))
    ho = bearer(login(c, world, "aa07other"))
    w = _hoa_ledger(c, h1, "972")
    plain_unit, special_unit = _unit(c, h1, w["property"], "01"), _unit(c, h1, w["property"], "02")
    p1, _ = _party(c, h1, "AA07Kaeufer")
    p2, _ = _party(c, h1, "AA07Erbe")
    # purchase in the year: regular case, no release needed
    _ownership(c, h1, plain_unit, p1, "2026-01-01", "purchase")
    special = _ownership(c, h1, special_unit, p2, "2026-03-01", "inheritance")
    st = _ok(
        c.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2026}, headers=h1), 201
    )
    sid = st["id"]

    def codes() -> list[str]:
        pkg = _ok(c.get(f"{H}/statements/{sid}/package", headers=h1))
        return [f["code"] for f in pkg["blocking"]]

    assert codes().count("acquisition_unreleased") == 1
    items = _ok(c.get(f"{H}/statements/{sid}/acquisitions", headers=h1))
    assert [(i["unit_number"], i["acquisition_kind"], i["status"]) for i in items["items"]] == [
        ("02", "inheritance", "open")
    ]
    assert "Erbfall" in items["items"][0]["allocation_proposal"]
    assert items["note"]

    base = f"{H}/statements/{sid}/acquisitions/{special['id']}"
    # no release without a request; reader may not request; other tenant sees nothing
    assert c.post(f"{base}/release", json={"note": "geprüft"}, headers=h2).status_code == 404
    assert c.post(f"{base}/request", json={}, headers=hr).status_code == 403
    assert c.post(f"{base}/request", json={}, headers=ho).status_code == 404
    assert c.post(f"{base}/request", json={"note": 5}, headers=h1).status_code == 422
    _ok(c.post(f"{base}/request", json={"note": "Erbschein liegt vor"}, headers=h1), 201)
    assert c.post(f"{base}/request", json={}, headers=h1).status_code == 409
    # same person cannot release; short note is invalid
    assert c.post(f"{base}/release", json={"note": "geprüft"}, headers=h1).status_code == 409
    assert c.post(f"{base}/release", json={"note": "x"}, headers=h2).status_code == 422
    assert codes().count("acquisition_unreleased") == 1  # requested only
    done = _ok(c.post(f"{base}/release", json={"note": "Erbschein geprüft"}, headers=h2))
    assert done["status"] == "released"
    assert "acquisition_unreleased" not in codes()
    assert c.post(f"{base}/release", json={"note": "nochmal"}, headers=h2).status_code == 409
