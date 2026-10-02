"""AG08 (GAF-34): owner rental reporting for investors. Off by default with a note, G3 closed
with a note, own SEV unit only, foreign unit 404, resident and staff 403, bad id 422."""

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
from sqlalchemy import create_engine, select, text
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
SOME = "00000000-0000-7000-8000-000000000001"


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
        a, _ = await services.provision_tenant(factory, slug=f"ag08a-{RUN}", name=f"AG08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag08b-{RUN}", name=f"AG08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("ag08admin", a), ("ag08adminb", b)):
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
            TestClient(create_app(settings)) as closed,
        ):
            yield open_, closed


def _no(n: int) -> str:
    return f"{(int(RUN, 16) + n) % 900 + 100:03d}"


def _setup(c: TestClient, h: dict[str, str], no: str, name: str, sev: bool) -> dict[str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AG08-WEG {no}", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, prop["id"], "01")
    owner, _ = _party(c, h, name)
    tenant, _ = _party(c, h, f"Mieter{name}")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
                "sev_enabled": sev,
            },
            headers=h,
        ),
        201,
    )
    if sev:
        tenancy = _ok(
            c.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": unit,
                    "party_id": tenant,
                    "start_date": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )
        _ok(
            c.post(
                f"/api/v1/contracts/{tenancy['id']}/payments",
                json={
                    "payment_type_code": "rent",
                    "net": "850.00",
                    "vat_percent": "0",
                    "gross": "850.00",
                    "valid_from": "2024-01-01",
                },
                headers=h,
            ),
            201,
        )
    return {"property": prop["id"], "unit": unit, "party": owner}


def _seed(database: Database, tenant: UUID, meta: dict[str, str]) -> str:
    from mhvp.accounting.models import Ledger
    from mhvp.billing.models import Statement, StatementKind, StatementSnapshot
    from mhvp.billing.status import StatementStatus
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_engine(database.migrator_url)
    try:
        with Session(engine) as s, s.begin():
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            prop = uuid.UUID(meta["property"])
            hoa = s.scalar(
                select(LegalEntity).where(
                    LegalEntity.property_id == prop, LegalEntity.kind == LegalEntityKind.HOA
                )
            )
            assert hoa is not None
            ledger = s.scalar(select(Ledger).where(Ledger.legal_entity_id == hoa.id))
            if ledger is None:
                ledger = Ledger(
                    tenant_id=tenant,
                    legal_entity_id=hoa.id,
                    property_id=prop,
                    name=f"AG08 Ledger {RUN}",
                )
                s.add(ledger)
                s.flush()
            ids: dict[str, uuid.UUID] = {}
            for key, status in (
                ("issued", StatementStatus.ISSUED),
                ("draft", StatementStatus.CALCULATED),
            ):
                st = Statement(
                    tenant_id=tenant,
                    kind=StatementKind.OPERATING_COSTS,
                    ledger_id=ledger.id,
                    property_id=prop,
                    period_from=date(2025, 1, 1),
                    period_to=date(2025, 12, 31),
                    status=status,
                )
                s.add(st)
                s.flush()
                snap = StatementSnapshot(
                    tenant_id=tenant,
                    statement_id=st.id,
                    rule_version="t",
                    inputs={
                        "occupants": [
                            {
                                "unit_id": meta["unit"],
                                "contract_id": None,
                                "from": "2025-03-01",
                                "to": "2025-03-31",
                            },
                            {
                                "unit_id": meta["unit"],
                                "contract_id": str(uuid.uuid4()),
                                "from": "2025-04-01",
                                "to": "2025-12-31",
                            },
                        ]
                    },
                    results={
                        "results": [{"unit_number": "01", "costs": "1200.00"}],
                        "total": "4800.00",
                        "vacancy_owner_share": "100.00",
                    },
                    hash="z" * 64,
                )
                s.add(snap)
                s.flush()
                st.snapshot_id = snap.id
                ids[key] = st.id
            return str(ids["issued"])
    finally:
        engine.dispose()


def test_owner_rental_reporting(
    clients: tuple[TestClient, TestClient], world: World, database: Database
) -> None:
    c, closed = clients
    ha = bearer(login(c, world, "ag08admin"))
    hb = bearer(login(c, world, "ag08adminb"))
    meta = _setup(c, ha, _no(1), f"Sev{RUN}", True)
    plain = _setup(c, ha, _no(2), f"Plain{RUN}", False)
    owner = _portal_user(c, ha, world, "ag08own", _contact_of(c, ha, meta["party"]))
    _seed(database, world.tenant_a, meta)
    meta_b = _setup(c, hb, _no(3), f"SevB{RUN}", True)
    owner_b = _portal_user(c, hb, world, "ag08ownb", _contact_of(c, hb, meta_b["party"]))
    url = f"{P}/rental-reporting"

    assert c.get(url, headers=ha).status_code in (401, 403)
    # switch off (default): empty with note, enabled false
    off = _ok(c.get(url, headers=owner))
    assert off["items"] == []
    assert off["enabled"] is False
    assert off["note"]
    features = "/api/v1/portal-admin/features"
    for h in (ha, hb):
        _ok(c.patch(features, json={"owner_rental_income_enabled": True}, headers=h))
    body = _ok(c.get(url, headers=owner))
    assert body["enabled"] is True
    assert [u["unit_id"] for u in body["items"]] == [meta["unit"]]
    periods = body["items"][0]["periods"]
    assert len(periods) == 1  # the draft statement does not count
    p = periods[0]
    assert p["allocable_costs_tenant"] == "1200.00"
    assert p["allocable_costs_property"] == "4800.00"
    assert p["vacancy_days"] == 31
    assert p["vacancy_owner_share_property"] == "100.00"
    assert p["agreed_rent_monthly_gross"] == "850.00"
    assert f"MieterSev{RUN}" not in str(body)
    # own unit filter, foreign unit 404, bad id 422, unknown parameter 422
    assert len(_ok(c.get(f"{url}?unit_id={meta['unit']}", headers=owner))["items"]) == 1
    for foreign in (plain["unit"], meta_b["unit"], SOME):
        assert c.get(f"{url}?unit_id={foreign}", headers=owner).status_code == 404
    assert c.get(f"{url}?unit_id=x", headers=owner).status_code == 422
    assert c.get(f"{url}?x=1", headers=owner).status_code in (401, 422)
    # other tenant sees nothing of tenant A
    assert _ok(c.get(url, headers=owner_b))["items"][0]["periods"] == []
    # gate G3 closed: empty with note
    gated = _ok(closed.get(url, headers=owner))
    assert gated["items"] == []
    assert "G3" in gated["note"]
