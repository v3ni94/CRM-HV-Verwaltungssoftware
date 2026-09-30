"""D11 (prior period from the migration journal, later period from the active journal) and
the acceptance record of the migration (13.1, M8-08, M8-09).

Expected figures fixed in advance (rule 0.1.8): expenses 400,00 EUR before and 600,00 EUR
after the cut off date 01.07.2026 give 1.000,00 EUR for the year; the opening balance entry
is no expense. Synthetic export headers."""

# ruff: noqa: F401, F811

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m8_import import XLSX, _stage, _xlsx
from tests.integration.test_m8_migration import (
    M,
    _code,
    _hoa,
    _ok,
    client,
    world,
)
from tests.integration.test_m10_ledger import A, _book, _entry, _line

pytestmark = pytest.mark.integration


def test_d11_year_expenses_prior_and_later_period(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "migadmin"))
    reader = bearer(login(client, world, "migreader"))
    other = bearer(login(client, world, "migother"))
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    _, ledger, acc, _ = _hoa(client, h, "871", template)
    accounts = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    expense = next(a for a in accounts if a["type"] == "expense")
    _ok(
        client.put(
            f"{M}/ledgers/{ledger}/cutoff", json={"migration_cutoff": "2026-07-01"}, headers=h
        )
    )
    rows = [
        ["Buchungsnummer", "Objekt", "Konto", "Datum", "Betrag", "Buchungstext", "Beleg"],
        ["E1", "871", expense["number"], "15.03.2026", "400,00", "Reinigung", "R-1"],
        ["E1", "871", "1200", "15.03.2026", "-400,00", "Reinigung", "R-1"],
    ]
    staged = _stage(client, h, "journal", "journal.xlsx", _xlsx(rows), XLSX)
    body = {"source_file_id": staged["id"], "year": 2026, "year_complete": True}
    _ok(client.post(f"{M}/ledgers/{ledger}/journal", json=body, headers=h))
    _book(
        client,
        h,
        ledger,
        _entry(
            "custom",
            "2026-09-10",
            [_line(expense["id"], "600"), _line(acc["001200"], "0", "600")],
        ),
    )
    view = _ok(client.get(f"{M}/ledgers/{ledger}/year-expenses?year=2026", headers=h))
    assert view["prior_period_total"] == "400.00"
    assert view["later_period_total"] == "600.00"
    assert view["total"] == "1000.00"
    assert view["prior_year_complete"] is True
    assert (
        client.get(f"{M}/ledgers/{ledger}/year-expenses?year=2026", headers=reader).status_code
        == 200
    )
    assert (
        client.get(f"{M}/ledgers/{ledger}/year-expenses?year=2026", headers=other).status_code
        == 404
    )
    assert client.get(f"{M}/ledgers/{ledger}/year-expenses?year=1900", headers=h).status_code == 422


def test_acceptance_record_lifecycle(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "migadmin"))
    reader = bearer(login(client, world, "migreader"))
    other = bearer(login(client, world, "migother"))
    second = bearer(login(client, world, "migacc"))
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)["id"]
    prop, _, _, _ = _hoa(client, h, "872", template)
    url = f"{M}/properties/{prop['id']}/acceptance"
    body = {
        "review_scope": "Salden, offene Posten, Kautionen",
        "responsible_persons": [{"name": "Test Prüfer", "role": "Buchhaltung"}],
        "non_migratable_data": "",
        "fallback_plan": "Weiterbetrieb im Altsystem bis zur Freigabe",
        "archive_concept": "",
    }
    assert client.post(url, json=body, headers=reader).status_code == 403
    assert client.post(url, json=body, headers=other).status_code == 404
    assert client.post(url, json={**body, "x": 1}, headers=h).status_code == 422
    item = _ok(client.post(url, json=body, headers=h), 201)
    sign = f"{M}/acceptance/{item['id']}/sign"
    incomplete = client.post(sign, headers=second)
    assert incomplete.status_code == 409
    assert _code(incomplete) == "MHVP-MIG-0002"
    body["archive_concept"] = "Archivierung der Exporte im DMS"
    _ok(client.put(f"{M}/acceptance/{item['id']}", json=body, headers=h))
    same_person = client.post(sign, headers=h)
    assert same_person.status_code == 403
    assert _code(same_person) == "MHVP-GATE-0002"
    signed = _ok(client.post(sign, headers=second))
    assert signed["status"] == "signed"
    assert client.put(f"{M}/acceptance/{item['id']}", json=body, headers=h).status_code == 409
    assert len(_ok(client.get(url, headers=reader))) == 1
