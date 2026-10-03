"""AF15 (GAC-01, GAC-03, GAF-33): owner portal reports. Owner statements rental/SEV only for the
own legal entity, only issued, only with G3 and the tenant switch (default off); explanations
and resolved economic plans only for own units with G4. Foreign ids 404, resident 403, bad id
422, other tenant sees nothing."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
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


class OpenG3G4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G3, ReleaseGate.G4)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af15a-{RUN}", name=f"AF15 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af15b-{RUN}", name=f"AF15 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("af15admin", a), ("af15adminb", b)):
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
            TestClient(create_app(settings, release_gate_resolver=OpenG3G4())) as open_,
            TestClient(create_app(settings)) as closed,
        ):
            yield open_, closed


def _no(n: int) -> str:
    return f"{(int(RUN, 16) + n) % 900 + 100:03d}"


def _owner(c: TestClient, h: dict[str, str], no: str, name: str) -> dict[str, str]:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AF15-WEG {no}", "management_type": "hoa"},
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
    return {"property": weg["id"], "party": party, "unit": unit}


def _seed(
    database: Database, tenant: UUID, meta: dict[str, str], other_unit: str
) -> dict[str, str]:
    """Owner statement (issued and draft), hoa statement and resolved plan written directly."""
    from mhvp.accounting.models import Ledger
    from mhvp.billing.owner_statement import (
        OwnerStatement,
        OwnerStatementKind,
        OwnerStatementStatus,
    )
    from mhvp.billing.status import StatementStatus
    from mhvp.hoa.models import EconomicPlan, HoaStatement, Resolution
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_engine(database.migrator_url)
    out: dict[str, str] = {}
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
            hoa_ledger = s.scalar(select(Ledger).where(Ledger.legal_entity_id == hoa.id))
            if hoa_ledger is None:
                hoa_ledger = Ledger(
                    tenant_id=tenant,
                    legal_entity_id=hoa.id,
                    property_id=prop,
                    name=f"AF15 Ledger {RUN}",
                )
                s.add(hoa_ledger)
                s.flush()
            own = LegalEntity(
                tenant_id=tenant,
                kind=LegalEntityKind.SEV_OWNER,
                name=f"AF15 SEV {RUN}",
                party_id=uuid.UUID(meta["party"]),
            )
            foreign = LegalEntity(
                tenant_id=tenant, kind=LegalEntityKind.SEV_OWNER, name=f"AF15 Fremd {RUN}"
            )
            s.add_all([own, foreign])
            s.flush()
            results = {
                "income": {"rent": "1000.00", "advances": "0", "other": "0", "total": "1000.00"},
                "expenses": {"lines": [], "total": "0.00"},
                "payouts": {"total": "800.00"},
                "admin_fee": {"net": "0.00", "vat": "0.00", "gross": "0.00"},
                "liquidity": {"free": "200.00"},
                "open_receivables": {"total": "0.00"},
                "deposits": {"held": "0.00"},
            }
            rows = {}
            for key, entity, status in (
                ("issued", own, OwnerStatementStatus.ISSUED),
                ("draft", own, OwnerStatementStatus.CALCULATED),
                ("foreign", foreign, OwnerStatementStatus.ISSUED),
            ):
                st = OwnerStatement(
                    tenant_id=tenant,
                    ledger_id=hoa_ledger.id,
                    legal_entity_id=entity.id,
                    property_id=prop,
                    kind=OwnerStatementKind.RENTAL_OWNER,
                    period_from=date(2025, 1, 1),
                    period_to=date(2025, 12, 31),
                    status=status,
                    snapshot={"results": results},
                    snapshot_hash="x" * 64,
                )
                s.add(st)
                rows[key] = st
            unit_snap = {
                "unit_id": meta["unit"],
                "unit_number": "01",
                "cost_share": "1200.00",
                "advances_resolved": "1000.00",
                "advances_paid": "900.00",
                "result": "200.00",
                "arrears": "100.00",
                "reserve_due": "300.00",
                "reserve_paid": "300.00",
            }
            other_snap = dict(unit_snap, unit_id=other_unit, unit_number="99")
            hs = HoaStatement(
                tenant_id=tenant,
                ledger_id=hoa_ledger.id,
                year=2025,
                version=1,
                status=StatementStatus.ISSUED,
                reserve_opening=Decimal("0"),
                reserve_withdrawals=Decimal("0"),
                reserve_interest=Decimal("0"),
                snapshot={
                    "units": [unit_snap, other_snap],
                    "reserve": {"opening": "0.00", "closing": "300.00"},
                },
                snapshot_hash="y" * 64,
                posted_entry_ids=[],
            )
            res = Resolution(
                tenant_id=tenant,
                legal_entity_id=hoa.id,
                number=1,
                decided_on=date(2025, 11, 1),
                subject="Wirtschaftsplan 2026",
                wording="beschlossen",
                status="positive",
                votes={},
            )
            # AP05 / GAL-107: an issued WEG statement needs its resolution (CHECK in 0462).
            s.add(res)
            s.flush()
            hs.resolution_id = res.id
            s.add(hs)
            s.flush()
            plan_unit = {
                "unit_id": meta["unit"],
                "unit_number": "01",
                "annual": {"hoa_fee": "1200.00", "reserve": "300.00"},
                "monthly": {"hoa_fee": "100.00", "reserve": "25.00"},
                "rounding_difference": {"hoa_fee": "0.00", "reserve": "0.00"},
            }
            for status, resolution in (
                (StatementStatus.RESOLVED, res.id),
                (StatementStatus.CALCULATED, None),
            ):
                s.add(
                    EconomicPlan(
                        tenant_id=tenant,
                        ledger_id=hoa_ledger.id,
                        year=2026,
                        valid_from=date(2026, 1, 1),
                        status=status,
                        version=1,
                        resolution_id=resolution,
                        snapshot={
                            "units": [plan_unit, dict(plan_unit, unit_id=other_unit)],
                            "totals": {"hoa_fee": "2400.00", "reserve": "600.00"},
                        },
                    )
                )
            s.flush()
            out = {k: str(v.id) for k, v in rows.items()}
    finally:
        engine.dispose()
    return out


def test_owner_reports_scope(
    clients: tuple[TestClient, TestClient], world: World, database: Database
) -> None:
    c, closed = clients
    ha = bearer(login(c, world, "af15admin"))
    hb = bearer(login(c, world, "af15adminb"))
    meta = _owner(c, ha, _no(1), f"Eigentuemer AF15 {RUN}")
    other = _owner(c, ha, _no(2), f"Fremd AF15 {RUN}")
    owner = _portal_user(c, ha, world, "af15own", _contact_of(c, ha, meta["party"]))
    ids = _seed(database, world.tenant_a, meta, other["unit"])
    # owner of tenant B: sees nothing of tenant A
    meta_b = _owner(c, hb, _no(3), f"Eigentuemer AF15B {RUN}")
    owner_b = _portal_user(c, hb, world, "af15ownb", _contact_of(c, hb, meta_b["party"]))

    # staff account without portal role: 403
    assert c.get(f"{P}/rental-statements", headers=ha).status_code in (401, 403)

    # switch off by default: empty list with note, PDF 403
    off = _ok(c.get(f"{P}/rental-statements", headers=owner))
    assert off["items"] == []
    assert off["enabled"] is False
    assert off["note"]
    assert c.get(f"{P}/rental-statements/{ids['issued']}/pdf", headers=owner).status_code == 403
    _ok(
        c.patch(
            "/api/v1/portal-admin/features",
            json={"owner_rental_statements_enabled": True},
            headers=ha,
        )
    )
    assert (
        c.patch(
            "/api/v1/portal-admin/features",
            json={"owner_rental_statements_enabled": "x"},
            headers=ha,
        ).status_code
        == 422
    )

    listed = _ok(c.get(f"{P}/rental-statements", headers=owner))
    assert [i["statement_id"] for i in listed["items"]] == [ids["issued"]]
    assert listed["items"][0]["payouts_total"] == "800.00"
    pdf = c.get(f"{P}/rental-statements/{ids['issued']}/pdf", headers=owner)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
    for sid in (ids["draft"], ids["foreign"], SOME):
        assert c.get(f"{P}/rental-statements/{sid}/pdf", headers=owner).status_code == 404
    assert c.get(f"{P}/rental-statements/x/pdf", headers=owner).status_code == 422
    # gate G3 closed: empty list with note, PDF 403
    gated = _ok(closed.get(f"{P}/rental-statements", headers=owner))
    assert gated["items"] == []
    assert "G3" in gated["note"]
    assert (
        closed.get(f"{P}/rental-statements/{ids['issued']}/pdf", headers=owner).status_code == 403
    )

    expl = _ok(c.get(f"{P}/statement-explanations", headers=owner))
    assert [(i["unit_id"], i["result"]) for i in expl["items"]] == [(meta["unit"], "200.00")]
    assert expl["texts"]["portal_owner_explain_result"]
    plans = _ok(c.get(f"{P}/plans", headers=owner))
    assert len(plans["items"]) == 1
    assert [u["unit_id"] for u in plans["items"][0]["units"]] == [meta["unit"]]
    assert plans["items"][0]["units"][0]["monthly"]["hoa_fee"] == "100.00"
    for path in ("statement-explanations", "plans"):
        body = _ok(closed.get(f"{P}/{path}", headers=owner))
        assert body["items"] == []
        assert "G4" in body["note"]
        assert _ok(c.get(f"{P}/{path}", headers=owner_b))["items"] == []
    assert _ok(c.get(f"{P}/rental-statements", headers=owner_b))["items"] == []
    assert c.get(f"{P}/rental-statements/{ids['issued']}/pdf", headers=owner_b).status_code in (
        403,
        404,
    )
    assert c.get(f"{P}/plans?x=1", headers=owner).status_code in (401, 422)
