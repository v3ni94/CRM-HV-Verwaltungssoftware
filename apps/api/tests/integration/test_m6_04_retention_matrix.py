"""M6-04 Aufbewahrungsmatrix produktiv (V17, 6.9.5, D46): Zuordnung Kategorie zu Profil mit
Fristberechnung, Sperre je Dokument und je Vorgang, Löschvorschlagslauf mit Vier-Augen-Freigabe,
Löschprotokoll und Mandantentrennung."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.documents.retention import propose_all_tenants_once
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import _ok, _profiles, _settings, _upload
from tests.integration.test_m6_documents import client as _m6_client
from tests.integration.test_m6_documents import s3 as _m6_s3

# The fixtures of test_m6_documents are re-exported under their own names (pytest needs the
# module attribute); ruff's F811 does not see the re-export as a use.
s3 = _m6_s3
client = _m6_client

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    """Own tenants and users (module scope): the fixture of test_m6_documents provisions
    fixed slugs and cannot run twice in one session."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r-{RUN}", name=f"Retention {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"s-{RUN}", name=f"Fremd R {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("r6admin", a, "tenant_admin"),
            ("r6second", a, "tenant_admin"),
            ("r6other", b, "tenant_admin"),
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


def _release(c: TestClient, world: World, profile_id: str) -> None:
    second = bearer(login(c, world, "r6second"))
    _ok(c.post(f"/api/v1/retention-profiles/{profile_id}/release", headers=second), 200)


def _released_profile(c: TestClient, world: World, h: dict[str, str], suffix: str) -> Any:
    profile = _ok(
        c.post(
            "/api/v1/retention-profiles",
            json={
                "document_class": f"m604_{suffix}_{RUN}",
                "legal_basis": "Testprofil ohne Rechtsquelle",
                "retention_years": 1,
                "start_rule": "end_of_year_created",
            },
            headers=h,
        )
    )
    _release(c, world, profile["id"])
    return profile


def _category(c: TestClient, h: dict[str, str], code: str, profile_id: str | None) -> Any:
    category = _ok(
        c.post("/api/v1/document-categories", json={"code": code, "name": code}, headers=h)
    )
    if profile_id:
        category = _ok(
            c.patch(
                f"/api/v1/document-categories/{category['id']}",
                json={"retention_profile_id": profile_id},
                headers=h,
            ),
            200,
        )
    return category


def _events(c: TestClient, h: dict[str, str], kind: str) -> list[dict[str, Any]]:
    return _ok(c.get("/api/v1/tenant/events", params={"type": kind}, headers=h), 200)  # type: ignore[no-any-return]


def test_category_mapping_computes_period_from_start_rule(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r6admin"))
    contracts = _profiles(client, h)["contracts"]
    category = _category(client, h, f"vertrag_{RUN}", contracts["id"])
    assert category["retention_profile_id"] == contracts["id"]
    doc = _ok(
        _upload(client, h, "mv.txt", b"Mietvertrag", "text/plain", category_id=category["id"])
    )
    # Contract end unknown: profile assigned, period not computable, deletion locked.
    assert doc["retention_profile_id"] == contracts["id"]
    assert doc["retention_until"] is None
    url = f"/api/v1/documents/{doc['id']}"
    _release(client, world, contracts["id"])
    refused = client.delete(url, headers=h)
    assert refused.status_code == 409
    assert "Fristbeginn fehlt" in refused.json()["detail"]
    # Contract end given: 10 years after the year end of the contract end.
    patched = _ok(client.patch(url, json={"retention_base_on": "2020-03-31"}, headers=h), 200)
    assert patched["retention_until"] == "2030-12-31"
    assert client.delete(url, headers=h).status_code == 409  # not expired
    # Uncategorised document with mapping applied later: end of creation year plus period.
    profile = _released_profile(client, world, h, "belege")
    plain = _ok(_upload(client, h, "beleg.txt", b"Beleg", "text/plain"))
    assert plain["retention_profile_id"] is None
    category2 = _category(client, h, f"beleg_{RUN}", None)
    moved = _ok(
        client.patch(
            f"/api/v1/documents/{plain['id']}", json={"category_id": category2["id"]}, headers=h
        ),
        200,
    )
    assert moved["retention_profile_id"] is None
    _ok(
        client.patch(
            f"/api/v1/document-categories/{category2['id']}",
            json={"retention_profile_id": profile["id"]},
            headers=h,
        ),
        200,
    )
    applied = _ok(client.post("/api/v1/retention-profiles/apply", headers=h), 200)
    assert applied["assigned"] >= 1
    after = _ok(client.get(f"/api/v1/documents/{plain['id']}", headers=h), 200)
    assert after["retention_profile_id"] == profile["id"]
    assert after["retention_until"] == f"{datetime.now(UTC).year + 1}-12-31"
    # Editing a released profile makes it a draft again (new release needed).
    edited = _ok(
        client.patch(
            f"/api/v1/retention-profiles/{profile['id']}", json={"retention_years": 2}, headers=h
        ),
        200,
    )
    assert edited["status"] == "entwurf"
    assert edited["review_note"]


def test_ticket_hold_blocks_deletion_of_linked_documents(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r6admin"))
    profile = _released_profile(client, world, h, "vorgang")
    ticket = _ok(client.post("/api/v1/tickets", json={"title": f"Streit {RUN}"}, headers=h))
    doc = _ok(
        _upload(
            client,
            h,
            "beweis.txt",
            b"Beweis",
            "text/plain",
            links=f'[{{"entity_type": "ticket", "entity_id": "{ticket["id"]}", "role": "evidence"}}]',
        )
    )
    url = f"/api/v1/documents/{doc['id']}"
    _ok(
        client.patch(
            url,
            json={"retention_profile_id": profile["id"], "retention_until": "2019-12-31"},
            headers=h,
        ),
        200,
    )
    held = _ok(
        client.post(
            f"/api/v1/tickets/{ticket['id']}/retention-hold",
            json={"reason": "Rechtsstreit anhängig"},
            headers=h,
        ),
        200,
    )
    assert held["retention_hold_reason"] == "Rechtsstreit anhängig"
    refused = client.delete(url, headers=h)
    assert refused.status_code == 409
    assert "Vorgang" in refused.json()["detail"]
    # A proposal run does not list a held document either.
    no_proposal = client.post("/api/v1/deletion-proposals", headers=h)
    assert no_proposal.status_code in (201, 409)
    if no_proposal.status_code == 201:
        assert doc["id"] not in {i["document_id"] for i in no_proposal.json()["items"]}
    _ok(
        client.request(
            "DELETE",
            f"/api/v1/tickets/{ticket['id']}/retention-hold",
            json={"reason": "Verfahren beendet"},
            headers=bearer(login(client, world, "r6second")),
        ),
        200,
    )
    assert client.delete(url, headers=h).status_code == 204
    events = _events(client, h, "ticket.hold_set")
    assert any(e["entity_id"] == ticket["id"] for e in events)


def test_proposal_four_eyes_log_and_recheck_at_execution(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r6admin"))
    second = bearer(login(client, world, "r6second"))
    other = bearer(login(client, world, "r6other"))
    profile = _released_profile(client, world, h, "lauf")
    due, kept = [], None
    for name in ("a", "b", "c"):
        doc = _ok(_upload(client, h, f"{name}.txt", f"Inhalt {name}".encode(), "text/plain"))
        _ok(
            client.patch(
                f"/api/v1/documents/{doc['id']}",
                json={"retention_profile_id": profile["id"], "retention_until": "2018-12-31"},
                headers=h,
            ),
            200,
        )
        due.append(doc)
    kept = due.pop()
    # The other tenant's document with the same expired date must never appear here.
    foreign = _ok(_upload(client, other, "fremd.txt", b"Fremd", "text/plain"))
    proposal = _ok(client.post("/api/v1/deletion-proposals", headers=h))
    ids = {i["document_id"] for i in proposal["items"]}
    assert {d["id"] for d in due} <= ids
    assert kept["id"] in ids
    assert foreign["id"] not in ids
    assert proposal["status"] == "open"
    assert proposal["created_by"] == str(world.users["r6admin"])
    # Four eyes: the initiator cannot approve, another tenant cannot see it.
    assert (
        client.post(f"/api/v1/deletion-proposals/{proposal['id']}/approve", headers=h).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/deletion-proposals/{proposal['id']}", headers=other).status_code == 404
    )
    approved = _ok(
        client.post(f"/api/v1/deletion-proposals/{proposal['id']}/approve", headers=second), 200
    )
    assert approved["status"] == "approved"
    assert approved["approved_by"] == str(world.users["r6second"])
    # The approver cannot execute; a hold set after the approval keeps the document.
    assert (
        client.post(
            f"/api/v1/deletion-proposals/{proposal['id']}/execute", headers=second
        ).status_code
        == 403
    )
    _ok(
        client.post(
            f"/api/v1/documents/{kept['id']}/hold",
            json={"reason": "Nachträgliche Sperre"},
            headers=h,
        ),
        200,
    )
    result = _ok(
        client.post(f"/api/v1/deletion-proposals/{proposal['id']}/execute", headers=h), 200
    )
    assert result["deleted"] >= len(due)
    assert result["skipped"] >= 1
    done = result["proposal"]
    assert done["status"] == "executed"
    assert done["executed_by"] == str(world.users["r6admin"])
    by_doc = {i["document_id"]: i for i in done["items"]}
    for doc in due:
        item = by_doc[doc["id"]]
        assert item["status"] == "deleted"
        assert item["sha256"] == doc["sha256"]
        assert item["deleted_at"]
        assert item["deleted_by"] == str(world.users["r6admin"])
        assert item["document_class"] == profile["document_class"]
        assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 404
    skipped = by_doc[kept["id"]]
    assert skipped["status"] == "skipped"
    assert "Löschungssperre" in skipped["skip_reason"]
    assert client.get(f"/api/v1/documents/{kept['id']}", headers=h).status_code == 200
    # Executed twice is refused; the log lists the run with its items.
    assert (
        client.post(f"/api/v1/deletion-proposals/{proposal['id']}/execute", headers=h).status_code
        == 409
    )
    listed = _ok(client.get("/api/v1/deletion-proposals", headers=h), 200)
    assert proposal["id"] in {p["id"] for p in listed}
    deleted_events = _events(client, h, "document.deleted")
    logged = [e for e in deleted_events if e["entity_id"] == due[0]["id"]]
    assert logged
    assert logged[0]["payload"]["approved_by"] == str(world.users["r6second"])
    assert logged[0]["payload"]["proposal_id"] == proposal["id"]
    assert client.get(f"/api/v1/documents/{foreign['id']}", headers=other).status_code == 200


def test_monthly_job_creates_a_proposal_per_tenant_without_deleting(
    client: TestClient, world: World, database: Any, redis_url: str
) -> None:
    h = bearer(login(client, world, "r6admin"))
    profile = _released_profile(client, world, h, "beat")
    doc = _ok(_upload(client, h, "monat.txt", b"Monat", "text/plain"))
    _ok(
        client.patch(
            f"/api/v1/documents/{doc['id']}",
            json={"retention_profile_id": profile["id"], "retention_until": "2017-12-31"},
            headers=h,
        ),
        200,
    )
    report = asyncio.run(propose_all_tenants_once(_settings(database, redis_url)))
    assert report["errors"] == []
    assert report["proposals"] >= 1
    open_ones = _ok(
        client.get("/api/v1/deletion-proposals", params={"status": "open"}, headers=h), 200
    )
    job_made = [p for p in open_ones if p["created_by"] is None]
    assert job_made
    assert doc["id"] in {i["document_id"] for p in job_made for i in p["items"]}
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=h).status_code == 200
    # A second run adds nothing while the proposal is open (no duplicate proposals).
    again = asyncio.run(propose_all_tenants_once(_settings(database, redis_url)))
    assert again["errors"] == []
    later = _ok(client.get("/api/v1/deletion-proposals", params={"status": "open"}, headers=h), 200)
    assert len(later) == len(open_ones)
    # Approval of a job proposal by one person, execution by another.
    second = bearer(login(client, world, "r6second"))
    target = job_made[0]["id"]
    _ok(client.post(f"/api/v1/deletion-proposals/{target}/approve", headers=second), 200)
    assert (
        client.post(f"/api/v1/deletion-proposals/{target}/execute", headers=second).status_code
        == 403
    )
    # Rejection is possible while open or approved and is logged.
    rejected = _ok(
        client.post(
            f"/api/v1/deletion-proposals/{target}/reject", json={"note": "Noch prüfen"}, headers=h
        ),
        200,
    )
    assert rejected["status"] == "rejected"
    assert rejected["note"] == "Noch prüfen"
