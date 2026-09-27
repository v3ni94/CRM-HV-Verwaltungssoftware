"""M40-02: preview endpoint for bved 3.10 exchange files of the file exchange providers
(Techem, Brunata Minol, BRUNATA-METRONA). Nothing is stored; authorization, provider check and
tenant module gate are verified."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import RUN, World, bearer, client, login
from tests.integration.test_m40_metering import _connection, _ok
from tests.unit.test_m40_metering_heiwako import PROP, d_line, encode, l_line, m_line

__all__ = ["client"]

pytestmark = pytest.mark.skipif(not RUN, reason="integration database not configured")


@pytest.fixture
def admin(client: TestClient, world: World) -> dict[str, str]:
    h = bearer(login(client, world, "admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"metering_module_enabled": True}, headers=h))
    return h


def _files() -> list[tuple[str, tuple[str, bytes, str]]]:
    dtm = encode(l_line(PROP, ("010125", "311225")), m_line(PROP, "0001", "Mustermann, Max"))
    dtd = encode(
        d_line(PROP, "0001", cost_type="001", total="850.25", prepaid="1200.00", balance="-349.75")
    )
    return [
        ("files", ("DTM310_20260927120000123.DAT", dtm, "application/octet-stream")),
        ("files", ("DTD310_20260927120000123.DAT", dtd, "application/octet-stream")),
    ]


def test_heiwako_preview_parses_files_and_stores_nothing(
    client: TestClient, admin: dict[str, str]
) -> None:
    conn = _connection(
        client, admin, "Techem Dateien", secrets=False, provider_code="techem", config={}
    )
    url = f"/api/v1/metering/connections/{conn['id']}/heiwako-import/preview"
    body: dict[str, Any] = _ok(client.post(url, files=_files(), headers=admin))
    assert body["adapter"] == "techem_file" and body["stored"] is False  # noqa: PT018
    assert body["errors"] == []
    assert {f["name"]: f["record_counts"] for f in body["files"]} == {
        "DTM310_20260927120000123.DAT": {"L": 1, "M": 1},
        "DTD310_20260927120000123.DAT": {"D": 1},
    }
    (result,) = body["billing_results"]
    assert result["external_billing_unit"] == PROP
    assert result["period_from"] == "2025-01-01" and result["period_to"] == "2025-12-31"  # noqa: PT018
    assert result["amount"] == "850.25" and result["balance_gross"] == "-349.75"  # noqa: PT018
    assert body["users"][0]["name"] == "Mustermann, Max"
    # Techem does not name D records publicly: reported, not refused
    dtd = next(f for f in body["files"] if f["kind"] == "DTD310")
    assert dtd["undocumented_record_types"] == ["D"]
    # nothing stored: no sync job, no billing result behind the connection
    jobs = _ok(client.get("/api/v1/metering/sync-jobs", headers=admin))
    assert all(j["connection_id"] != conn["id"] for j in jobs)
    # capability matrix keeps every online function unimplemented
    detail = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=admin))
    assert all(not row["adapter_implemented"] for row in detail["capabilities"])


def test_heiwako_preview_refuses_online_providers_and_readers(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    ista = _connection(client, admin, "ista", provider_code="ista")
    response = client.post(
        f"/api/v1/metering/connections/{ista['id']}/heiwako-import/preview",
        files=_files(),
        headers=admin,
    )
    assert response.status_code == 422, response.text
    techem = _connection(client, admin, "Techem", secrets=False, provider_code="techem", config={})
    reader = bearer(login(client, world, "reader"))
    response = client.post(
        f"/api/v1/metering/connections/{techem['id']}/heiwako-import/preview",
        files=_files(),
        headers=reader,
    )
    assert response.status_code == 403, response.text
