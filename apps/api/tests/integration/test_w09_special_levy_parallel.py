"""GAM-609 (rule 0.1.9): instalment run of a special levy applied twice in parallel and after
an abort. Fixed expectation: one unit (MEA 1.000 of 1.000), total 1.200,00 EUR in 3
instalments from 01.03.2026 -> 3 x 400,00 = 1.200,00 EUR, exactly three contract payments of
type special_levy (March, April, May 2026), no duplicate."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login
from tests.integration.test_m24_hoa import _owner
from tests.integration.test_w09_special_levy import A, H, _ok, _world

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


def test_levy_installments_parallel(world: World, database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings)) as client:
        h = bearer(login(client, world, "w09admin"))
        prop = _ok(
            client.post(
                "/api/v1/properties",
                json={"number": "796", "name": "WEG Parallel", "management_type": "hoa"},
                headers=h,
            ),
            201,
        )
        hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
        keys = {
            k["code"]: k["id"]
            for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
        }
        _unit, contract = _owner(client, h, prop["id"], "01", "1000", keys["MEA"], {})
        template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
        ledger = _ok(
            client.post(
                f"{A}/ledgers",
                json={"legal_entity_id": hoa, "template_id": template["id"]},
                headers=h,
            ),
            201,
        )["id"]
        use = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/accounts",
                json={
                    "number": "049900",
                    "name": "Aufzug",
                    "category": "cost",
                    "type": "expense",
                },
                headers=h,
            ),
            201,
        )["id"]
        lid = _ok(
            client.post(
                f"{H}/special-levies",
                json={
                    "ledger_id": ledger,
                    "purpose": "Aufzug",
                    "total": "1200.00",
                    "allocation_key_id": keys["MEA"],
                    "first_due": "2026-03-01",
                    "instalments": 3,
                    "account_id": use,
                },
                headers=h,
            ),
            201,
        )["id"]
        calc = _ok(client.post(f"{H}/special-levies/{lid}/calculate", headers=h))
        (unit,) = calc["snapshot"]["units"]
        assert [i["amount"] for i in unit["instalments"]] == ["400.00"] * 3
        resolution = _ok(
            client.post(
                f"{H}/resolutions",
                json={
                    "legal_entity_id": hoa,
                    "decided_on": "2026-02-10",
                    "subject": "Sonderumlage Aufzug",
                    "wording": "Sonderumlage für den Aufzug wird beschlossen.",
                    "status": "positive",
                    "subject_type": "special_levy",
                    "subject_id": lid,
                    "snapshot_hash": calc["snapshot_hash"],
                },
                headers=h,
            ),
            201,
        )["id"]
        _ok(
            client.post(
                f"{H}/special-levies/{lid}/resolve",
                json={"resolution_id": resolution},
                headers=h,
            )
        )
        apply = f"{H}/special-levies/{lid}/apply"

        def levy_payments() -> list[dict[str, Any]]:
            rows = _ok(client.get(f"/api/v1/contracts/{contract['id']}/payments", headers=h))
            return [r for r in rows if r["payment_type_code"] == "special_levy"]

        # Abort: the event write raises after the payments were added; all rolled back.
        async def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("synthetic abort")

        with (
            patch("mhvp.hoa.levies.emit", boom),
            TestClient(create_app(settings), raise_server_exceptions=False) as broken,
        ):
            assert broken.post(apply, headers=h).status_code == 500
        assert _ok(client.get(f"{H}/special-levies/{lid}", headers=h))["status"] == "resolved"
        assert levy_payments() == []

        # Parallel: both calls answer, exactly one creates the instalments.
        def apply_in_own_client(_: int) -> Any:
            with TestClient(create_app(settings)) as own:
                return own.post(apply, headers=h)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply_in_own_client, [1, 2]))
        assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
        assert sum(r.json().get("payments_created", 0) for r in results) == 3

        rows = levy_payments()
        assert sorted((r["valid_from"], r["gross"]) for r in rows) == [
            ("2026-03-01", "400.00"),
            ("2026-04-01", "400.00"),
            ("2026-05-01", "400.00"),
        ]
        assert sum(Decimal(r["gross"]) for r in rows) == Decimal("1200.00")
