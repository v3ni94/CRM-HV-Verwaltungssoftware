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
