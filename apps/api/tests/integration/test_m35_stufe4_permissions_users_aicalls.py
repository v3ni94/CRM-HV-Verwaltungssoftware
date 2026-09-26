"""M35 Stufe 4 (docs/plans/M35-objektakte-uebernahme.md section 4, docs/rules/M35-03.md):
objektakte permission keys enforced on the review/rules/completeness routers (role templates
`standard`, `technical_clerk`, `read_only`, `tenant_admin`), the user/role mapping proposal of
the objektakte import (report only, no user is created), `decided_by` resolution of taken over
review decisions, and the read-only AI call protocol per document incl. tenant separation."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.main import create_app
from mhvp.objektakte.models import DocumentReviewDecision
from mhvp.platform import services
from mhvp.platform.models import User
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
IMPORTS = "/api/v1/objektakte/imports"
RULES = "/api/v1/objektakte/classification-rules"
REVIEW = "/api/v1/objektakte/review"
REQUIRED = "/api/v1/objektakte/required-documents"


def _dump(world: World) -> str:
    """objektakte export with the Stufe 4 tables: `roles`, `users` (the clerk's e-mail matches
    an existing CRM member, the admin's does not, one deleted user, one unknown role) and
    `ai_calls`, plus one document with a review case and two decisions."""
    clerk_email = world.email("s4clerk")
    return rf"""
INSERT INTO `objects_managedobject` (`id`,`object_number`,`name`,`street`,`house_number`,
`postal_code`,`city`,`management_type`)
VALUES (12,'712','Haus Stufe vier','Musterweg','4','40721','Hilden','weg');

INSERT INTO `roles` (`id`,`code`,`name`,`permissions`,`is_system`)
VALUES (1,'admin','Admin','["settings.write","review.decide"]',1),
(2,'sachbearbeiter','Sachbearbeiter','["review.decide"]',1),
(3,'gast','Gast','[]',0);

INSERT INTO `users` (`id`,`email`,`display_name`,`role_id`,`password_hash`,`status`,
`deleted_at`,`google_subject`)
VALUES (501,'alt-admin-{RUN}@example.org','Alt Admin',1,'pbkdf2$secret','active',NULL,NULL),
(502,'{clerk_email}','Sach Bearbeiter',2,'pbkdf2$secret','active',NULL,NULL),
(503,'weg-{RUN}@example.org','Geloescht',2,'pbkdf2$secret','disabled','2026-01-01 10:00:00',NULL),
(504,'gast-{RUN}@example.org','Gast Nutzer',3,NULL,'invited',NULL,NULL);

INSERT INTO `documents_documentcategory` (`code`,`folder_name`,`display_name`,`sort_order`)
VALUES ('03','03_Vertraege','Verträge',30);

INSERT INTO `documents_document` (`id`,`object_id`,`sha256`,`size_bytes`,`mime_type`,
`original_name`,`current_name`,`drive_file_id`,`drive_node_id`,`status`,
`duplicate_of_document_id`,`category_code`,`subfolder_id`,`document_type_id`,`ocr_cache_key`)
VALUES (1101,12,'d4e5f6',1024,'application/pdf','vertrag4.pdf','Vertrag4.pdf',
'drv-file-1101',NULL,'ocr_done',NULL,'03',NULL,NULL,'cache-1101');

INSERT INTO `review_reviewcase` (`id`,`document_id`,`case_type`,`candidates`,`proposed_action`,
`priority`,`status`,`snoozed_until`)
VALUES (2101,1101,'category_ambiguous',NULL,NULL,70,'resolved',NULL);

INSERT INTO `review_reviewdecision` (`id`,`review_case_id`,`document_id`,`decision_type`,
`decided_by`,`decided_at`,`before_state`,`after_state`)
VALUES (3101,2101,1101,'accept',502,'2026-03-01 09:00:00','{{"status":"open"}}','{{"category":"03"}}'),
(3102,2101,1101,'accept',501,'2026-03-02 09:00:00',NULL,'{{"category":"03"}}');

INSERT INTO `ai_calls` (`id`,`object_id`,`document_id`,`run_id`,`job_id`,`purpose`,`provider`,
`model`,`endpoint`,`region`,`page_from`,`page_to`,`prompt_hash`,`prompt_chars`,
`masked_entities_count`,`tokens_in`,`tokens_out`,`cost_eur`,`price_list_version`,`duration_ms`,
`status`,`http_status`,`error_message`,`fallback_used`,`fallback_of_call_id`,`response_summary`,
`requested_at`)
VALUES (7001,12,1101,NULL,NULL,'classify','openai','gpt-4o-mini','https://api.example/v1','eu',
1,2,'abc123',1200,3,800,50,'0.001200','2026-01',900,'ok',200,NULL,0,NULL,
'{{"category":"03","confidence":0.91}}','2026-02-10 08:00:00'),
(7002,12,1101,NULL,NULL,'extract_entities','anthropic','claude-x',NULL,'eu',NULL,NULL,'def456',
300,0,200,20,'0.000300',NULL,400,'error',500,'Anbieterfehler',1,NULL,NULL,'2026-02-11 08:00:00'),
(7003,12,NULL,NULL,NULL,'assign_object','openai','gpt-4o-mini',NULL,NULL,NULL,NULL,NULL,NULL,0,
NULL,NULL,NULL,NULL,NULL,'ok',200,NULL,0,NULL,NULL,'2026-02-12 08:00:00');
"""


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"s4-{RUN}", name=f"S4 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"s4b-{RUN}", name=f"S4 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("s4admin", a, "tenant_admin"),
            ("s4clerk", a, "standard"),
            ("s4tech", a, "technical_clerk"),
            ("s4reader", a, "read_only"),
            ("s4other", b, "tenant_admin"),
        ):
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(client: TestClient, world: World, headers: dict[str, str], mode: str) -> Any:
    return client.post(
        IMPORTS,
        params={"mode": mode},
        files={"file": ("dump.sql", _dump(world).encode("utf-8"), "application/sql")},
        headers=headers,
    )


# --- (1) permission keys ------------------------------------------------------------------


def test_me_lists_objektakte_permissions_per_role(client: TestClient, world: World) -> None:
    clerk = _ok(client.get("/api/v1/auth/me", headers=bearer(login(client, world, "s4clerk"))))
    assert {"objektakte:read", "objektakte:update", "objektakte:approve"} <= set(
        clerk["permissions"]
    )
    assert "objektakte:delete" not in clerk["permissions"]

    tech = _ok(client.get("/api/v1/auth/me", headers=bearer(login(client, world, "s4tech"))))
    assert {"objektakte:read", "objektakte:update"} <= set(tech["permissions"])
    assert "objektakte:approve" not in tech["permissions"]

    reader = _ok(client.get("/api/v1/auth/me", headers=bearer(login(client, world, "s4reader"))))
    assert "objektakte:read" in reader["permissions"]
    assert "objektakte:update" not in reader["permissions"]


def test_rules_require_approve_and_delete_keys(client: TestClient, world: World) -> None:
    rule = {"name": "Stufe 4", "pattern_type": "filename_regex", "pattern_value": r"vertrag"}
    reader = bearer(login(client, world, "s4reader"))
    _ok(client.get(RULES, headers=reader))
    assert client.post(RULES, json=rule, headers=reader).status_code == 403

    tech = bearer(login(client, world, "s4tech"))
    _ok(client.get(RULES, headers=tech))
    assert client.post(RULES, json=rule, headers=tech).status_code == 403

    clerk = bearer(login(client, world, "s4clerk"))
    created = _ok(client.post(RULES, json=rule, headers=clerk), 201)
    _ok(client.patch(f"{RULES}/{created['id']}", json={"active": False}, headers=clerk))
    # Deleting stays with the tenant administrator (docs/rules/M2-07.md).
    assert client.delete(f"{RULES}/{created['id']}", headers=clerk).status_code == 403
    admin = bearer(login(client, world, "s4admin", world.tenant_a))
    assert client.delete(f"{RULES}/{created['id']}", headers=admin).status_code == 204


def test_required_documents_follow_the_same_keys(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "s4admin", world.tenant_a))
    cat = _ok(
        client.post(
            "/api/v1/document-categories",
            json={"code": "s4", "name": "Stufe vier"},
            headers=admin,
        ),
        201,
    )
    body = {"management_type": "rental", "document_category_id": cat["id"], "mandatory": True}
    tech = bearer(login(client, world, "s4tech"))
    _ok(client.get(REQUIRED, headers=tech))
    assert client.post(REQUIRED, json=body, headers=tech).status_code == 403
    clerk = bearer(login(client, world, "s4clerk"))
    row = _ok(client.post(REQUIRED, json=body, headers=clerk), 201)
    assert client.delete(f"{REQUIRED}/{row['id']}", headers=clerk).status_code == 403
    assert client.delete(f"{REQUIRED}/{row['id']}", headers=admin).status_code == 204


def test_review_center_requires_update_key_to_decide(client: TestClient, world: World) -> None:
    reader = bearer(login(client, world, "s4reader"))
    _ok(client.get(REVIEW, headers=reader))
    resp = client.post(
        f"{REVIEW}/bulk-decide",
        json={
            "case_ids": ["00000000-0000-0000-0000-000000000001"],
            "category_id": "00000000-0000-0000-0000-000000000002",
        },
        headers=reader,
    )
    assert resp.status_code == 403
    tech = bearer(login(client, world, "s4tech"))
    resp = client.post(
        f"{REVIEW}/bulk-decide",
        json={
            "case_ids": ["00000000-0000-0000-0000-000000000001"],
            "category_id": "00000000-0000-0000-0000-000000000002",
        },
        headers=tech,
    )
    # technical_clerk holds objektakte:update; the unknown case is reported, not forbidden.
    assert _ok(resp)["missing"] == ["00000000-0000-0000-0000-000000000001"]


# --- (2) user/role mapping proposal ---------------------------------------------------------


async def _user_exists(settings: Any, email: str) -> bool:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            return await session.scalar(select(User.id).where(User.email == email)) is not None
    finally:
        await engine.dispose()


def _by_source(mapping: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {m["source_id"]: m for m in mapping}


def test_preview_and_apply_report_user_mapping_without_creating_users(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "s4admin", world.tenant_a))
    preview = _ok(_upload(client, world, admin, "preview"))
    assert preview["counts"]["users"] == 4
    assert preview["ai_calls"] == 3
    rows = _by_source(preview["user_mapping"])
    assert rows["501"]["proposed_role"] == "tenant_admin"
    assert rows["501"]["action"] == "invite"
    assert rows["501"]["crm_user_id"] is None
    assert rows["502"]["proposed_role"] == "standard"
    assert rows["502"]["action"] == "already_member"
    assert rows["502"]["crm_user_id"] == str(world.users["s4clerk"])
    assert rows["502"]["crm_member_roles"] == ["standard"]
    assert rows["503"]["action"] == "skip"
    assert rows["503"]["objektakte_status"] == "deleted"
    assert rows["504"]["action"] == "manual"
    assert rows["504"]["proposed_role"] is None
    assert rows["504"]["objektakte_role"] == "gast"
    for row in rows.values():
        assert "password_hash" not in row
        assert "google_subject" not in row

    applied = _ok(_upload(client, world, admin, "apply"))
    assert _by_source(applied["user_mapping"]) == rows
    assert applied["created"]["ai_calls"] == 3
    assert applied["created"]["review_reviewdecision"] == 2
    # Proposal only: no CRM user was created for the unknown objektakte accounts.
    settings = _settings(database, redis_url)
    assert not asyncio.run(_user_exists(settings, f"alt-admin-{RUN}@example.org"))
    assert not asyncio.run(_user_exists(settings, f"gast-{RUN}@example.org"))
    # The report is persisted with the import run.
    fetched = _ok(client.get(f"{IMPORTS}/{applied['import_run_id']}", headers=admin))
    assert _by_source(fetched["user_mapping"]) == rows


async def _decisions(settings: Any, tenant_id: Any) -> list[DocumentReviewDecision]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = (
                (
                    await session.execute(
                        select(DocumentReviewDecision).where(
                            DocumentReviewDecision.source_system == "objektakte"
                        )
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)
    finally:
        await engine.dispose()


def test_decided_by_resolves_only_existing_members(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "s4admin", world.tenant_a))
    _ok(_upload(client, world, admin, "apply"))
    rows = {
        r.source_id: r
        for r in asyncio.run(_decisions(_settings(database, redis_url), world.tenant_a))
    }
    assert rows["3101"].decided_by == world.users["s4clerk"]
    before_state_3101 = rows["3101"].before_state
    assert before_state_3101 is not None
    assert before_state_3101["source_decided_by"] == "502"
    assert before_state_3101["status"] == "open"
    assert rows["3102"].decided_by is None
    before_state_3102 = rows["3102"].before_state
    assert before_state_3102 is not None
    assert before_state_3102["source_decided_by"] == "501"


# --- (3) AI call protocol, read-only per document ------------------------------------------


def test_ai_calls_visible_per_document_read_only_and_tenant_separated(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "s4admin", world.tenant_a))
    applied = _ok(_upload(client, world, admin, "apply"))
    doc_id = applied["id_map"]["documents_document"]["1101"]

    reader = bearer(login(client, world, "s4reader"))
    body = _ok(client.get(f"/api/v1/objektakte/documents/{doc_id}/ai-calls", headers=reader))
    assert body["count"] == 2  # call 7003 has no document
    assert [i["source_id"] for i in body["items"]] == ["7002", "7001"]
    first = body["items"][1]
    assert first["provider"] == "openai"
    assert first["cost_eur"] == "0.001200"
    assert first["masked_entities_count"] == 3
    assert first["response_summary"] == {"category": "03", "confidence": 0.91}
    assert first["requested_at"].startswith("2026-02-10T08:00:00")
    assert body["items"][0]["fallback_used"] is True
    assert body["items"][0]["error_message"] == "Anbieterfehler"
    assert body["total_cost_eur"] == "0.001500"
    assert body["total_tokens_in"] == 1000

    again = _ok(_upload(client, world, admin, "apply"))
    assert again["skipped_duplicates"]["ai_calls"] == 3
    assert "ai_calls" not in again["created"]

    other = bearer(login(client, world, "s4other", world.tenant_b))
    resp = client.get(f"/api/v1/objektakte/documents/{doc_id}/ai-calls", headers=other)
    assert resp.status_code == 404
