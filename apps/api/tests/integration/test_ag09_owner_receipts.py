"""AG09 / GAF-36: owner receipt search (switch, G4, scope, document authorisation)."""

import asyncio
import uuid
from collections.abc import Iterator
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
from tests.integration.test_m21_portal import _contact_of, _doc, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal/owner"
SOME = "00000000-0000-7000-8000-000000000001"


class OpenG4:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G4,)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag09a-{RUN}", name=f"AG09 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag09b-{RUN}", name=f"AG09 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("ag09admin", a), ("ag09adminb", b)):
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
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
            TestClient(create_app(settings)) as closed,
        ):
            yield open_, closed


def _no(n: int) -> str:
    return f"{(int(RUN, 16) + n) % 900 + 100:03d}"


def _owner(c: TestClient, h: dict[str, str], no: str, name: str) -> dict[str, str]:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"AG09-WEG {no}", "management_type": "hoa"},
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


PA_F = "/api/v1/portal-admin/features"


def _hoa_entity(database: Database, tenant: UUID, prop: str) -> str:
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    engine = create_engine(database.migrator_url)
    try:
        with Session(engine) as s, s.begin():
            s.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            row = s.scalar(
                select(LegalEntity).where(
                    LegalEntity.property_id == uuid.UUID(prop),
                    LegalEntity.kind == LegalEntityKind.HOA,
                )
            )
            assert row is not None
            return str(row.id)
    finally:
        engine.dispose()


def _seed(database: Database, tenant: UUID, meta: dict[str, str], docs: dict[str, str]) -> str:
    from mhvp.accounting.models import Ledger
    from mhvp.billing.status import StatementStatus
    from mhvp.hoa.models import HoaCostItem, HoaStatement
    from mhvp.properties.models import AllocationKey, LegalEntity, LegalEntityKind

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
                    tenant_id=tenant, legal_entity_id=hoa.id, property_id=prop, name=f"AG09 {RUN}"
                )
                s.add(ledger)
                s.flush()
            key = AllocationKey(
                tenant_id=tenant,
                property_id=prop,
                code="AG09",
                name="AG09 MEA",
                unit_of_measure="mea",
                kind="static",
            )
            s.add(key)
            s.flush()
            ids: dict[int, Any] = {}
            for year, version, status in (
                (2024, 1, StatementStatus.ISSUED),
                (2025, 1, StatementStatus.ISSUED),
                (2025, 2, StatementStatus.ISSUED),
                (2026, 1, StatementStatus.CALCULATED),
            ):
                st = HoaStatement(
                    tenant_id=tenant,
                    ledger_id=ledger.id,
                    year=year,
                    version=version,
                    status=status,
                    reserve_opening=Decimal("0"),
                    reserve_withdrawals=Decimal("0"),
                    reserve_interest=Decimal("0"),
                    snapshot={"units": []},
                    snapshot_hash="y" * 64,
                    posted_entry_ids=[],
                )
                s.add(st)
                s.flush()
                ids[year * 10 + version] = st.id
            for sid, label, doc in (
                (ids[20251], "Alt V1", docs["visible"]),
                (ids[20252], "Hausmeister", docs["visible"]),
                (ids[20252], "Versicherung", docs["hidden"]),
                (ids[20252], "Ohne Beleg", None),
                (ids[20241], "Reinigung", docs["visible"]),
                (ids[20261], "Entwurf", docs["visible"]),
            ):
                s.add(
                    HoaCostItem(
                        tenant_id=tenant,
                        statement_id=sid,
                        label=label,
                        amount=Decimal("100.00"),
                        allocation_key_id=key.id,
                        basis="GO",
                        document_id=uuid.UUID(doc) if doc else None,
                    )
                )
            return str(ids[20252])
    finally:
        engine.dispose()


def test_owner_receipts(
    clients: tuple[TestClient, TestClient], world: World, database: Database
) -> None:
    c, closed = clients
    ha = bearer(login(c, world, "ag09admin"))
    hb = bearer(login(c, world, "ag09adminb"))
    meta = _owner(c, ha, _no(1), f"Eigentuemer AG09 {RUN}")
    other = _owner(c, ha, _no(2), f"Fremd AG09 {RUN}")

    entity = _hoa_entity(database, world.tenant_a, meta["property"])
    docs = {
        "visible": _doc(c, ha, "Beleg Hausmeister", "legal_entity", entity, ["owner"]),
        "hidden": _doc(c, ha, "Beleg intern", "legal_entity", entity, ["board"]),
    }
    owner = _portal_user(c, ha, world, "ag09own", _contact_of(c, ha, meta["party"]))
    _seed(database, world.tenant_a, meta, docs)
    meta_b = _owner(c, hb, _no(3), f"Eigentuemer AG09B {RUN}")
    owner_b = _portal_user(c, hb, world, "ag09ownb", _contact_of(c, hb, meta_b["party"]))
    assert other["unit"]

    assert c.get(f"{P}/receipts", headers=ha).status_code in (401, 403)
    assert c.get(f"{P}/receipts?bogus=1", headers=owner).status_code == 422
    # switch off by default
    off = _ok(c.get(f"{P}/receipts", headers=owner))
    assert off["items"] == []
    assert off["enabled"] is False
    assert off["note"]
    _ok(c.patch(PA_F, json={"portal_owner_receipts_enabled": True}, headers=ha))
    assert c.patch(PA_F, json={"portal_owner_receipts_enabled": "x"}, headers=ha).status_code == 422
    # gate G4 closed
    gated = _ok(closed.get(f"{P}/receipts", headers=owner))
    assert gated["items"] == []
    assert "G4" in gated["note"]

    got = _ok(c.get(f"{P}/receipts", headers=owner))
    assert got["enabled"] is True
    assert got["years"] == [2025, 2024]
    by = {(i["year"], i["label"]): i for i in got["items"]}
    # latest version per year only, no draft year, no item without receipt
    assert set(by) == {(2025, "Hausmeister"), (2025, "Versicherung"), (2024, "Reinigung")}
    assert by[(2025, "Hausmeister")]["available"] is True
    assert by[(2025, "Hausmeister")]["document_id"] == docs["visible"]
    assert by[(2025, "Versicherung")]["available"] is False
    assert by[(2025, "Versicherung")]["document_id"] is None
    assert by[(2025, "Versicherung")]["document_title"] is None
    assert [i["label"] for i in _ok(c.get(f"{P}/receipts?year=2024", headers=owner))["items"]] == [
        "Reinigung"
    ]
    assert [i["label"] for i in _ok(c.get(f"{P}/receipts?q=hausm", headers=owner))["items"]] == [
        "Hausmeister"
    ]
    assert c.get(f"{P}/receipts?year=abc", headers=owner).status_code == 422
    # retrieval through the existing document route writes the read receipt
    dl = c.get(f"/api/v1/portal/documents/{docs['visible']}/download", headers=owner)
    assert dl.status_code == 200
    assert (
        c.get(f"/api/v1/portal/documents/{docs['hidden']}/download", headers=owner).status_code
        == 404
    )
    # other tenant: switch off and nothing visible
    assert _ok(c.get(f"{P}/receipts", headers=owner_b))["items"] == []
