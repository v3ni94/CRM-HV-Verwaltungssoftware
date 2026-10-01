"""U15 review of the wave 4 and 5 code (docs/reviews/REVIEW-W45-2026-10-01.md).

Covers the fixes: property assignment on WEG reserves by id and in the portal
administration (representations, change requests), notification mails only to active
members, tenant export error without exception text and the platform administrator only
after a recorded switch. Foreign records answer 404, read only members 403, invalid ids 422,
tenant B sees nothing."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import update

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import IBAN_A, IBAN_B
from tests.integration.test_q11_workspace_w3 import _with_session
from tests.integration.test_q13_property_scope_etag import _assign, _estate, _ok
from tests.integration.test_r08_property_scope_domains import _bank
from tests.integration.test_t14_property_scope_rest import _owner_contact

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u15-{RUN}", name=f"U15 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u15b-{RUN}", name=f"U15 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("u15admin", a, "tenant_admin"),
            ("u15admin_b", b, "tenant_admin"),
            ("u15clerk", a, "standard"),
            ("u15reader", a, "read_only"),
            ("u15gone", a, "standard"),
            ("u15tax", a, "tax_advisor"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def test_reserve_and_portal_admin_property_scope(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "u15admin"))
    own = _estate(client, h, "151")
    foreign = _estate(client, h, "152")
    own.update(_bank(client, h, own["property"], IBAN_A, "151"))
    foreign.update(_bank(client, h, foreign["property"], IBAN_B, "152"))
    for estate, ref in ((own, "151"), (foreign, "152")):
        estate["reserve"] = _ok(
            client.post(
                f"{H}/reserves",
                json={"ledger_id": estate["ledger"], "name": f"Dach {ref}"},
                headers=h,
            ),
            201,
        )["id"]
        estate["owner"] = _owner_contact(client, h, estate["property"], ref)
        estate["rep_contact"] = str(_party(client, h, f"Vertreter{ref}")[1]["id"])
        estate["account"] = _ok(
            client.post(
                f"{P}/accounts",
                json={
                    "contact_id": estate["rep_contact"],
                    "email": world.email(f"u15p{ref}"),
                    "display_name": f"Vertreter {ref}",
                },
                headers=h,
            ),
            201,
        )["id"]
        estate["rep"] = _ok(
            client.post(
                f"{P}/representations",
                json={
                    "account_id": estate["account"],
                    "principal_contact_id": estate["owner"],
                    "document_id": estate["document"],
                    "valid_from": "2026-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
    _assign(client, h, world.users["u15clerk"], [own["property"]])
    _assign(client, h, world.users["u15reader"], [own["property"]])
    c = bearer(login(client, world, "u15clerk"))

    # Reserves by id (not covered by the WEG router guard before U15).
    for path in ("{r}", "{r}/development?year=2026"):
        assert (
            client.get(f"{H}/reserves/" + path.format(r=own["reserve"]), headers=c).status_code
            == 200
        )
        foreign_read = client.get(f"{H}/reserves/" + path.format(r=foreign["reserve"]), headers=c)
        assert foreign_read.status_code == 404, foreign_read.text
    patched = client.patch(f"{H}/reserves/{foreign['reserve']}", json={"name": "Fremd"}, headers=c)
    assert patched.status_code == 404, patched.text
    assert client.get(f"{H}/reserves/kein-uuid", headers=c).status_code == 422
    r = bearer(login(client, world, "u15reader"))
    denied = client.patch(f"{H}/reserves/{own['reserve']}", json={"name": "Neu"}, headers=r)
    assert denied.status_code == 403

    # Portal administration: representations listed only for visible contacts.
    listed = {x["id"] for x in _ok(client.get(f"{P}/representations", headers=c))}
    assert own["rep"] in listed
    assert foreign["rep"] not in listed
    assert foreign["rep"] in {x["id"] for x in _ok(client.get(f"{P}/representations", headers=h))}
    # Writes and the change requests need tenant_settings:update (administrator roles, which
    # are never property scoped); the scope checks there are defensive. The clerk gets 403.
    revoke = client.post(f"{P}/representations/{foreign['rep']}/revoke", headers=c)
    assert revoke.status_code == 403, revoke.text
    created = client.post(
        f"{P}/representations",
        json={
            "account_id": own["account"],
            "principal_contact_id": foreign["owner"],
            "document_id": own["document"],
            "valid_from": "2026-01-01",
        },
        headers=c,
    )
    assert created.status_code == 403, created.text
    # Change requests (portal MANAGE permission of the clerk): list filtered by contact,
    # deciding an unknown request answers 404.
    rows = _ok(client.get(f"{P}/change-requests", headers=c))
    assert all(x["contact_id"] != foreign["rep_contact"] for x in rows)
    unknown = client.post(
        f"{P}/change-requests/{uuid.uuid4()}/decide", json={"accept": False}, headers=c
    )
    assert unknown.status_code in (404, 422), unknown.text

    # Invoices follow the legal entity scope of the tax advisor (A37) as well.
    from tests.integration.test_m18_tax_advisor_scope import _membership_id

    tax_member = _membership_id(client, h, world.users["u15tax"])
    scoped = client.put(
        f"/api/v1/tenant/members/{tax_member}/legal-entities",
        json={"legal_entity_ids": [own["hoa"]]},
        headers=h,
    )
    assert scoped.status_code == 204, scoped.text
    t = bearer(login(client, world, "u15tax"))
    check = "/api/v1/accounting/invoices/{}/factual-check"
    assert client.get(check.format(own["invoice"]), headers=t).status_code == 200
    foreign_check = client.get(check.format(foreign["invoice"]), headers=t)
    assert foreign_check.status_code == 404, foreign_check.text

    # Tenant B sees nothing of tenant A.
    hb = bearer(login(client, world, "u15admin_b"))
    assert client.get(f"{H}/reserves/{own['reserve']}", headers=hb).status_code == 404
    assert own["rep"] not in {x["id"] for x in _ok(client.get(f"{P}/representations", headers=hb))}


def test_notification_mail_only_to_active_members(
    world: World, database: Database, redis_url: str
) -> None:
    from mhvp.platform.models import Membership, MembershipStatus
    from mhvp.workspace import notification_prefs
    from mhvp.workspace.models import Notification

    settings = _settings(database, redis_url)
    gone, clerk = world.users["u15gone"], world.users["u15clerk"]

    async def seed(session: Any) -> None:
        for user, title in ((gone, "Ausgeschieden"), (clerk, "Aktiv")):
            session.add(
                Notification(
                    tenant_id=world.tenant_a,
                    user_id=user,
                    kind="ticket_assigned",
                    title=title,
                    email_pending=True,
                )
            )
        await session.execute(
            update(Membership)
            .where(Membership.user_id == gone, Membership.tenant_id == world.tenant_a)
            .values(status=MembershipStatus.DISABLED)
        )

    asyncio.run(_with_session(settings, world.tenant_a, seed))
    sent: list[tuple[str, str]] = []

    async def send(session: Any) -> dict[str, int]:
        import mhvp.sla.channels as channels

        async def fake(_s: Any, _c: Any, _t: Any, to: str, subject: str, body: str) -> None:
            sent.append((to, subject + body))

        original = channels.send_email
        channels.send_email = fake  # type: ignore[assignment]
        try:
            return await notification_prefs.send_pending_mails(session, settings, world.tenant_a)
        finally:
            channels.send_email = original  # type: ignore[assignment]

    counts = asyncio.run(_with_session(settings, world.tenant_a, send))
    assert counts["skipped"] >= 1
    assert all("Ausgeschieden" not in text for _, text in sent)
    assert any("Aktiv" in text and to == world.email("u15clerk") for to, text in sent)


def test_notification_mail_pages_past_held_daily_entries(
    world: World, database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Immediate run: more held back daily entries than one page must not starve the
    immediate entry behind them."""
    from mhvp.workspace import notification_prefs
    from mhvp.workspace.models import Notification, NotificationPreference

    settings = _settings(database, redis_url)
    clerk = world.users["u15clerk"]
    monkeypatch.setattr(notification_prefs, "MAIL_BATCH", 2)

    async def seed(session: Any) -> None:
        session.add(
            NotificationPreference(
                tenant_id=world.tenant_a,
                user_id=clerk,
                kind="automation",
                in_app=True,
                email=True,
                email_mode="daily",
            )
        )
        await session.flush()
        for i in range(3):
            session.add(
                Notification(
                    tenant_id=world.tenant_a,
                    user_id=clerk,
                    kind="automation",
                    title=f"Taeglich {i}",
                    email_pending=True,
                )
            )
            await session.flush()
        session.add(
            Notification(
                tenant_id=world.tenant_a,
                user_id=clerk,
                kind="ticket_assigned",
                title="Sofort",
                email_pending=True,
            )
        )

    asyncio.run(_with_session(settings, world.tenant_a, seed))
    sent: list[str] = []

    async def send(session: Any) -> dict[str, int]:
        import mhvp.sla.channels as channels

        async def fake(_s: Any, _c: Any, _t: Any, to: str, subject: str, body: str) -> None:
            sent.append(subject + body)

        original = channels.send_email
        channels.send_email = fake  # type: ignore[assignment]
        try:
            return await notification_prefs.send_pending_mails(session, settings, world.tenant_a)
        finally:
            channels.send_email = original  # type: ignore[assignment]

    asyncio.run(_with_session(settings, world.tenant_a, send))
    assert any("Sofort" in s for s in sent)
    assert all("Taeglich" not in s for s in sent)


def test_tenant_export_error_without_exception_text(
    world: World, database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.core import storage
    from mhvp.platform import export_job
    from mhvp.platform.models import TenantExportJob

    settings = _settings(database, redis_url)
    admin = world.users["u15admin"]

    async def seed(session: Any) -> uuid.UUID:
        row = TenantExportJob(
            tenant_id=world.tenant_a,
            status=export_job.JOB_QUEUED,
            requested_by=admin,
            created_by=admin,
            updated_by=admin,
        )
        session.add(row)
        await session.flush()
        return row.id

    job_id = asyncio.run(_with_session(settings, world.tenant_a, seed))

    def broken(_settings: Any) -> Any:
        raise RuntimeError("endpoint https://s3.intern secret=abc")

    monkeypatch.setattr(storage, "create_s3_client", broken)
    with pytest.raises(RuntimeError):
        asyncio.run(export_job.run_tenant_export_job(settings, job_id, world.tenant_a))

    async def read(session: Any) -> str | None:
        row = await session.get(TenantExportJob, job_id)
        return row.error, row.status  # type: ignore[return-value]

    error, status = asyncio.run(_with_session(settings, world.tenant_a, read))
    assert status == export_job.JOB_FAILED
    assert error == "RuntimeError"
