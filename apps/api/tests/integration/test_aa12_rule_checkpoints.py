"""AA12: dated check points as draft register entries (GA08-02, GA08-03)."""

from fastapi.testclient import TestClient

from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m18_reports import _ok
from tests.integration.test_p10_reports import A, client, world  # noqa: F401


def test_seed_checkpoints_idempotent_draft_only(client: TestClient, world: World) -> None:  # noqa: F811
    h = bearer(login(client, world, "p10admin"))
    tax = bearer(login(client, world, "p10tax"))
    other = bearer(login(client, world, "p10other"))
    assert client.post(f"{A}/rule-versions/seed-checkpoints", headers=tax).status_code == 403
    first = _ok(client.post(f"{A}/rule-versions/seed-checkpoints", headers=h), 200)
    assert {r["rule_id"] for r in first} == {
        "H03-HeizkostenV-5",
        "H03-HeizkostenV-12",
        "H05-CO2KostAufG-5a-5d",
    }
    assert all(r["status"] == "draft" and r["expert_confirmed_by"] is None for r in first)
    assert sorted(r["effective_from"][:4] for r in first if r["rule_id"].startswith("H05")) == [
        "2028",
        "2029",
    ]
    assert _ok(client.post(f"{A}/rule-versions/seed-checkpoints", headers=h), 200) == []
    mine = _ok(
        client.get(f"{A}/rule-versions", params={"rule_id": "H05-CO2KostAufG-5a-5d"}, headers=h),
        200,
    )
    assert len(mine) == 2
    foreign = _ok(
        client.get(
            f"{A}/rule-versions", params={"rule_id": "H05-CO2KostAufG-5a-5d"}, headers=other
        ),
        200,
    )
    assert foreign == []


def test_due_checkpoints_hint_only(client: TestClient, world: World) -> None:  # noqa: F811
    """AB10 GA08-02: only reached check points are reported; read right suffices, no lock."""
    h = bearer(login(client, world, "p10admin"))
    tax = bearer(login(client, world, "p10tax"))
    other = bearer(login(client, world, "p10other"))
    body = {
        "rule_id": "AB10-pruefpunkt",
        "title": "Prüfpunkt Test",
        "effective_from": "2027-03-01",
        "case_groups": ["Prüfpunkt"],
        "source_status": "Entwurf",
    }
    _ok(client.post(f"{A}/rule-versions", json=body, headers=h), 201)
    path = f"{A}/rule-versions/due-checkpoints"
    early = _ok(client.get(path, params={"on": "2027-02-28"}, headers=tax), 200)
    assert "AB10-pruefpunkt" not in {r["rule_id"] for r in early}
    due = _ok(client.get(path, params={"on": "2027-03-01"}, headers=tax), 200)
    assert "AB10-pruefpunkt" in {r["rule_id"] for r in due}
    assert _ok(client.get(path, params={"on": "2027-03-01"}, headers=other), 200) == []
