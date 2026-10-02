"""AG12 (AF15-R, AF25-02): portal owner grant for pure rental owners (``property_owner``
without ownership contract) and the scope of ``GET /portal/owner/rental-statements``.

A rental owner sees the issued statements of the own ``rental_owner`` legal entity only, never
the statement of another owner of the tenant; the grant ends with the owner period (resync).
A statement whose legal entity is the community itself is shown to its owners only with the
switch ``owner_hoa_rental_statements_enabled`` (default off). Tenant B sees nothing."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal/owner"
PA = "/api/v1/portal-admin"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag12a-{RUN}", name=f"AG12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag12b-{RUN}", name=f"AG12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("ag12admin", a), ("ag12adminb", b)):
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
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings, release_gate_resolver=OpenG3())) as c:
            yield c


def _no(n: int) -> str:
    return f"{(int(RUN, 16) + n) % 900 + 100:03d}"


def _rental(c: TestClient, h: dict[str, str], no: str, name: str) -> dict[str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AG12-MV {no}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(c, h, name)
    owner = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": party, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    return {"property": prop["id"], "party": party, "entity": str(owner["legal_entity_id"])}


def _hoa_owner(c: TestClient, h: dict[str, str], no: str, name: str) -> dict[str, str]:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AG12-WEG {no}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, weg["id"], "01")
    party, _ = _party(c, h, name)
    _ok(
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
    return {"property": weg["id"], "party": party}


def _statement(database: Database, tenant: UUID, entity_id: str, property_id: str) -> str:
    from mhvp.accounting.models import Ledger
    from mhvp.billing.owner_statement import (
        OwnerStatement,
        OwnerStatementKind,
        OwnerStatementStatus,
    )

    engine = create_engine(database.migrator_url)
    try:
        with Session(engine) as s, s.begin():
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            entity = uuid.UUID(entity_id)
            ledger = s.scalar(select(Ledger).where(Ledger.legal_entity_id == entity))
            if ledger is None:
                ledger = Ledger(
                    tenant_id=tenant,
                    legal_entity_id=entity,
                    property_id=uuid.UUID(property_id),
                    name=f"AG12 Ledger {RUN} {entity_id[:8]}",
                )
                s.add(ledger)
                s.flush()
            st = OwnerStatement(
                tenant_id=tenant,
                ledger_id=ledger.id,
                legal_entity_id=entity,
                property_id=uuid.UUID(property_id),
                kind=OwnerStatementKind.RENTAL_OWNER,
                period_from=date(2025, 1, 1),
                period_to=date(2025, 12, 31),
                status=OwnerStatementStatus.ISSUED,
                snapshot={
                    "results": {
                        "income": {
                            "rent": "500.00",
                            "advances": "0",
                            "other": "0",
                            "total": "500.00",
                        },
                        "expenses": {"lines": [], "total": "0.00"},
                        "payouts": {"total": "500.00"},
                        "admin_fee": {"net": "0.00", "vat": "0.00", "gross": "0.00"},
                        "liquidity": {"free": "0.00"},
                        "open_receivables": {"total": "0.00"},
                        "deposits": {"held": "0.00"},
                    }
                },
                snapshot_hash="z" * 64,
            )
            s.add(st)
            s.flush()
            return str(st.id)
    finally:
        engine.dispose()


def _end_owner(database: Database, tenant: UUID, party: str) -> None:
    from mhvp.properties.models import PropertyOwner

    engine = create_engine(database.migrator_url)
    try:
        with Session(engine) as s, s.begin():
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            s.execute(
                update(PropertyOwner)
                .where(PropertyOwner.party_id == uuid.UUID(party))
                .values(valid_to=date(2021, 12, 31))
            )
    finally:
        engine.dispose()


def _ids(c: TestClient, h: dict[str, str]) -> list[str]:
    return [i["statement_id"] for i in _ok(c.get(f"{P}/rental-statements", headers=h))["items"]]


def test_rental_owner_grant_and_hoa_switch(
    client: TestClient, world: World, database: Database
) -> None:
    c = client
    ha = bearer(login(c, world, "ag12admin"))
    hb = bearer(login(c, world, "ag12adminb"))
    own = _rental(c, ha, _no(1), f"Vermieter AG12 {RUN}")
    other = _rental(c, ha, _no(2), f"Fremdvermieter AG12 {RUN}")
    weg = _hoa_owner(c, ha, _no(3), f"WEG AG12 {RUN}")
    renter = _portal_user(c, ha, world, "ag12mv", _contact_of(c, ha, own["party"]))
    member = _portal_user(c, ha, world, "ag12weg", _contact_of(c, ha, weg["party"]))
    own_b = _rental(c, hb, _no(4), f"Vermieter AG12B {RUN}")
    renter_b = _portal_user(c, hb, world, "ag12mvb", _contact_of(c, hb, own_b["party"]))

    st_own = _statement(database, world.tenant_a, own["entity"], own["property"])
    st_other = _statement(database, world.tenant_a, other["entity"], other["property"])
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_engine(database.migrator_url)
    with Session(engine) as s, s.begin():
        s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)})
        hoa = s.scalar(
            select(LegalEntity.id).where(
                LegalEntity.property_id == uuid.UUID(weg["property"]),
                LegalEntity.kind == LegalEntityKind.HOA,
            )
        )
    engine.dispose()
    assert hoa is not None
    st_hoa = _statement(database, world.tenant_a, str(hoa), weg["property"])

    # The rental owner now holds an owner grant (before: 403); switch off: empty list.
    off = _ok(c.get(f"{P}/rental-statements", headers=renter))
    assert off["items"] == []
    assert off["enabled"] is False
    _ok(c.patch(f"{PA}/features", json={"owner_rental_statements_enabled": True}, headers=ha))
    _ok(c.patch(f"{PA}/features", json={"owner_rental_statements_enabled": True}, headers=hb))

    assert _ids(c, renter) == [st_own]
    pdf = c.get(f"{P}/rental-statements/{st_own}/pdf", headers=renter)
    assert pdf.status_code == 200, pdf.text
    for sid in (st_other, st_hoa):
        assert c.get(f"{P}/rental-statements/{sid}/pdf", headers=renter).status_code == 404
    # WEG owners do not see the community's own statement by default (AF25-02).
    assert _ids(c, member) == []
    assert c.get(f"{P}/rental-statements/{st_hoa}/pdf", headers=member).status_code == 404
    # A pure rental owner has no WEG view.
    assert c.get(f"{P}/plans", headers=renter).status_code == 403

    # Tenant B: own statement list empty, foreign id 404.
    assert _ids(c, renter_b) == []
    assert c.get(f"{P}/rental-statements/{st_own}/pdf", headers=renter_b).status_code == 404

    # Switch for community statements: reader 403, bad value 422, admin on.
    body = {"owner_hoa_rental_statements_enabled": True}
    assert _ok(c.get(f"{PA}/features", headers=ha))["owner_hoa_rental_statements_enabled"] is False
    assert (
        c.patch(
            f"{PA}/features", json={"owner_hoa_rental_statements_enabled": "x"}, headers=ha
        ).status_code
        == 422
    )
    _ok(c.patch(f"{PA}/features", json=body, headers=ha))
    assert _ids(c, member) == [st_hoa]
    assert _ids(c, renter) == [st_own]
    assert _ids(c, renter_b) == []

    # Owner change: the owner period ends, a resync revokes the grant (403).
    _end_owner(database, world.tenant_a, own["party"])
    acc = _ok(c.get(f"{PA}/accounts?contact_id={_contact_of(c, ha, own['party'])}", headers=ha))[0]
    _ok(c.post(f"{PA}/accounts/{acc['id']}/sync-grants", headers=ha))
    assert c.get(f"{P}/rental-statements", headers=renter).status_code == 403
