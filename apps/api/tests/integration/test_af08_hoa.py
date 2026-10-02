"""AF08 (wave 17): GAA-02, GAE-11, GAE-12.

Expected values by hand:
* GAA-02: unit 01 owner A (contact A) asks for inspection on 01.03.2026, unrelated contact C
  too. Ownership transfer to B on 01.05.2026 -> scan notes exactly the request of A (1 note),
  status stays ``requested``; a second scan notes nothing (idempotent); C gets no note.
* GAE-11: a payment bound to a reserve of another GdWE is 422; the own reserve is 201.
* GAE-12: levy 1.000,00 on unit 01 (MEA 1000, one instalment 01.03.2026, resolution
  10.02.2026), transfer by inheritance to B on 01.05.2026, amendment to 1.200,00 due
  01.07.2026 -> difference +200,00 charged to: manual_release B, by_due_date B,
  by_resolution_date A (owner on the resolution day).
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import _settings
from tests.integration.test_m21_portal_owner import _ok
from tests.integration.test_m24_hoa import _hoa_ledger

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
C = "/api/v1/contracts"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af08a-{RUN}", name=f"AF08 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af08b-{RUN}", name=f"AF08 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af08admin", a, "tenant_admin"),
            ("af08reader", a, "read_only"),
            ("af08other", b, "tenant_admin"),
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ownership(c: TestClient, h: dict[str, str], unit: str, party: str) -> dict[str, Any]:
    return dict(
        _ok(
            c.post(
                C,
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
    )


def _transfer(c: TestClient, h: dict[str, str], contract: str, party: str, kind: str) -> Any:
    return _ok(
        c.post(
            f"{C}/{contract}/ownership-transfer",
            json={
                "new_party_id": party,
                "title_transfer_date": "2026-05-01",
                "acquisition_kind": kind,
                "carry_over_amounts": True,
            },
            headers=h,
        ),
        201,
    )


def test_gaa02_ownership_transfer_marks_open_inspection_requests(
    client: TestClient, world: World
) -> None:
    c = client
    h = bearer(login(c, world, "af08admin"))
    reader = bearer(login(c, world, "af08reader"))
    other = bearer(login(c, world, "af08other"))
    w = _hoa_ledger(c, h, "861")
    unit = _unit(c, h, w["property"], "01")
    party_a, contact_a = _party(c, h, "AF08EigA")
    party_b, _ = _party(c, h, "AF08EigB")
    _, contact_c = _party(c, h, "AF08Dritter")
    owner = _ownership(c, h, unit, party_a)
    reqs = {}
    for key, contact in (("a", contact_a), ("c", contact_c)):
        reqs[key] = _ok(
            c.post(
                f"{H}/inspection-requests",
                json={
                    "legal_entity_id": w["hoa"],
                    "applicant_contact_id": contact["id"],
                    "requested_on": "2026-03-01",
                    "scope_kinds": ["statement"],
                },
                headers=h,
            ),
            201,
        )["id"]
    scan = f"{H}/inspection-requests/ownership-transfers/scan"
    assert _ok(c.post(scan, headers=h)) == {"events": 0, "noted": 0}
    _transfer(c, h, owner["id"], party_b, "purchase")
    assert c.post(scan, headers=reader).status_code == 403
    assert _ok(c.post(scan, headers=h)) == {"events": 1, "noted": 1}
    assert _ok(c.post(scan, headers=h)) == {"events": 1, "noted": 0}  # idempotent
    got = _ok(c.get(f"{H}/inspection-requests/{reqs['a']}", headers=h))
    assert got["status"] == "requested"  # hint only, never closed
    notes = [e for e in got["events"] if e["source_event_id"]]
    assert len(notes) == 1
    assert notes[0]["kind"] == "owner_check"
    assert "01.05.2026" in notes[0]["note"]
    untouched = _ok(c.get(f"{H}/inspection-requests/{reqs['c']}", headers=h))
    assert not [e for e in untouched["events"] if e["source_event_id"]]
    # tenant separation: the other tenant sees no event and no request
    assert _ok(c.post(scan, headers=other)) == {"events": 0, "noted": 0}
    assert c.get(f"{H}/inspection-requests/{reqs['a']}", headers=other).status_code == 404


def test_gae11_payment_reserve_of_foreign_gdwe_is_422(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "af08admin"))
    own = _hoa_ledger(c, h, "862")
    foreign = _hoa_ledger(c, h, "863")
    reserve_own = _ok(
        c.post(f"{H}/reserves", json={"ledger_id": own["ledger"], "name": "Dach"}, headers=h), 201
    )["id"]
    reserve_foreign = _ok(
        c.post(f"{H}/reserves", json={"ledger_id": foreign["ledger"], "name": "Dach"}, headers=h),
        201,
    )["id"]
    party, _ = _party(c, h, "AF08Ruecklage")
    contract = _ownership(c, h, _unit(c, h, own["property"], "01"), party)
    body = {
        "payment_type_code": "reserve",
        "net": "50.00",
        "gross": "50.00",
        "valid_from": "2026-01-01",
    }
    bad = c.post(
        f"{C}/{contract['id']}/payments", json={**body, "reserve_id": reserve_foreign}, headers=h
    )
    assert bad.status_code == 422, bad.text
    good = _ok(
        c.post(
            f"{C}/{contract['id']}/payments", json={**body, "reserve_id": reserve_own}, headers=h
        ),
        201,
    )
    assert good["reserve_id"] == reserve_own
    _ok(c.put(f"{H}/reserve-payment-settings", json={"mode": "plan_ratio_proposal"}, headers=h))
    try:
        out = _ok(c.get(f"{H}/ledgers/{own['ledger']}/reserve-payments?year=2026", headers=h))
        assert out["mode"] == "plan_ratio_proposal"
        assert [r["reserve_id"] for r in out["reserves"]] == [reserve_own]
        assert "paid_proposal" in out["reserves"][0]
    finally:
        _ok(c.put(f"{H}/reserve-payment-settings", json={"mode": "bound_only"}, headers=h))


@pytest.mark.parametrize(
    ("number", "variant", "debtor"),
    [
        ("871", "manual_release", "new"),
        ("872", "by_due_date", "new"),
        ("873", "by_resolution_date", "old"),
    ],
)
def test_gae12_levy_difference_after_ownership_change(
    client: TestClient, world: World, number: str, variant: str, debtor: str
) -> None:
    c = client
    h = bearer(login(c, world, "af08admin"))
    w = _hoa_ledger(c, h, number)
    unit = _unit(c, h, w["property"], "01")
    _ok(
        c.post(
            f"/api/v1/units/{unit}/allocation-values",
            json={
                "allocation_key_id": w["keys"]["MEA"],
                "value": "1000",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )
    party_a, _ = _party(c, h, f"AF08Alt{number}")
    party_b, _ = _party(c, h, f"AF08Erbe{number}")
    old = _ownership(c, h, unit, party_a)
    use = _ok(
        c.post(
            f"/api/v1/accounting/ledgers/{w['ledger']}/accounts",
            json={"number": "049900", "name": "Dach", "category": "cost", "type": "expense"},
            headers=h,
        ),
        201,
    )["id"]

    def resolution(levy_id: str, hash_: str) -> str:
        return str(
            _ok(
                c.post(
                    f"{H}/resolutions",
                    json={
                        "legal_entity_id": w["hoa"],
                        "decided_on": "2026-02-10",
                        "subject": "Sonderumlage Dach",
                        "wording": "Sonderumlage für die Dachsanierung wird beschlossen.",
                        "status": "positive",
                        "subject_type": "special_levy",
                        "subject_id": levy_id,
                        "snapshot_hash": hash_,
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )

    def resolve_and_apply(levy_id: str) -> dict[str, Any]:
        calc = _ok(c.post(f"{H}/special-levies/{levy_id}/calculate", headers=h))
        rid = resolution(levy_id, calc["snapshot_hash"])
        _ok(c.post(f"{H}/special-levies/{levy_id}/resolve", json={"resolution_id": rid}, headers=h))
        return {
            "calc": calc,
            "applied": _ok(c.post(f"{H}/special-levies/{levy_id}/apply", headers=h)),
        }

    levy = _ok(
        c.post(
            f"{H}/special-levies",
            json={
                "ledger_id": w["ledger"],
                "purpose": "Dach",
                "total": "1000.00",
                "allocation_key_id": w["keys"]["MEA"],
                "first_due": "2026-03-01",
                "instalments": 1,
                "account_id": use,
            },
            headers=h,
        ),
        201,
    )
    assert resolve_and_apply(levy["id"])["applied"]["payments_created"] == 1
    new = _transfer(c, h, old["id"], party_b, "inheritance")
    _ok(c.put(f"{H}/acquisition-rules/inheritance", json={"variant": variant}, headers=h))
    try:
        amended = _ok(
            c.post(
                f"{H}/special-levies/{levy['id']}/amend",
                json={"total": "1200.00", "difference_due": "2026-07-01", "reason": "Nachtrag"},
                headers=h,
            ),
            201,
        )
        result = resolve_and_apply(amended["id"])
        (row,) = result["calc"]["snapshot"]["units"]
        assert row["difference"] == "200.00"
        assert result["applied"]["charges_created"] == 1
    finally:
        _ok(
            c.put(
                f"{H}/acquisition-rules/inheritance", json={"variant": "manual_release"}, headers=h
            )
        )
    target = new["id"] if debtor == "new" else old["id"]
    others = old["id"] if debtor == "new" else new["id"]

    def july(contract: str) -> list[dict[str, Any]]:
        rows = _ok(c.get(f"{C}/{contract}/payments", headers=h))
        return [
            p
            for p in rows
            if p["payment_type_code"] == "special_levy" and p["valid_from"] == "2026-07-01"
        ]

    assert [p["gross"] for p in july(target)] == ["200.00"]
    assert july(others) == []
