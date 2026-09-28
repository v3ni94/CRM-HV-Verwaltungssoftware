"""Folgevorgang statt Wiedereröffnung (Regel M19-10, Betreiberentscheidung 28.09.2026).

A new mail for a finished ticket reopens it only when the ticket was closed at most
``tenant_settings.ticket_reopen_window_days`` calendar days ago (default 30, boundary day
included). Closed longer ago: a follow-up ticket with a link to its predecessor, property,
unit and contact of the predecessor as preset and a note in both tickets. Automatic replies
neither reopen nor create a follow-up; the same mail processed twice creates one follow-up;
the setting and the tickets stay within their tenant.

Expected results are independent: the calendar day distance is set explicitly by backdating
``resolved_at`` to noon (operator time zone) of ``today - N`` days, so N is the distance."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, time, timedelta
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail_approval import _upload

pytestmark = pytest.mark.integration
T = "/api/v1/tickets"
M = "/api/v1/mail"
SETTINGS = "/api/v1/tenant/settings"
_LOCAL = ZoneInfo("Europe/Berlin")


def _eml(
    sender: str,
    subject: str,
    msg_id: str,
    *,
    in_reply_to: str | None = None,
    auto_submitted: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if auto_submitted:
        msg["Auto-Submitted"] = auto_submitted
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Das Fenster schließt wieder nicht.")
    return bytes(msg)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tfu-{RUN}", name=f"Folge {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"tfu2-{RUN}", name=f"Folge2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("tfuadmin", "tenant_admin", a),
            ("tfureader", "read_only", a),
            ("tfuotherb", "tenant_admin", b),
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
def settings(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url)


@pytest.fixture
def client(settings: Any) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _mailbox(client: TestClient, h: dict[str, str], address: str) -> Any:
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "fu"}, headers=h
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    return box


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, mailbox_id: str) -> Any:
    eml = _upload(client, h, f"{uuid.uuid4().hex}.eml", raw)
    return _ok(
        client.post(f"{M}/ingest", json={"document_id": eml, "mailbox_id": mailbox_id}, headers=h),
        201,
    )


def _backdate(settings: Any, tenant_id: uuid.UUID, ticket_id: str, days_ago: int) -> None:
    """``resolved_at`` at noon of ``today - days_ago`` in the operator time zone (the API
    never lets a user set it); through the RLS tenant scope like a request."""
    from sqlalchemy import update

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.tickets.models import Ticket

    closed = datetime.combine(local_today() - timedelta(days=days_ago), time(12), tzinfo=_LOCAL)

    async def _run() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                result = await session.execute(
                    update(Ticket)
                    .where(Ticket.id == uuid.UUID(ticket_id))
                    .values(resolved_at=closed)
                )
                assert result.rowcount == 1  # type: ignore[attr-defined]
        finally:
            await engine.dispose()

    asyncio.run(_run())


class Case:
    """A mail ticket of ``world`` closed ``days_ago`` calendar days ago."""

    def __init__(
        self,
        client: TestClient,
        settings: Any,
        world: World,
        tag: str,
        days_ago: int,
        *,
        admin: str = "tfuadmin",
        tenant: uuid.UUID | None = None,
    ) -> None:
        self.client = client
        self.h = bearer(login(client, world, admin))
        self.box = _mailbox(client, self.h, f"info-fu-{tag}-{RUN}@example.com")
        self.sender = f"mieter-fu-{tag}-{RUN}@example.com"
        self.tag = tag
        self.first_id = f"<fu-{tag}-1-{RUN}@x>"
        msg = _ingest(
            client, self.h, _eml(self.sender, f"Fenster {tag}", self.first_id), self.box["id"]
        )
        ref = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=self.h), 201)
        self.ticket_id, self.number = str(ref["ticket_id"]), int(ref["number"])
        _ok(
            client.patch(
                f"{T}/{self.ticket_id}",
                json={
                    "assignee_user_id": str(world.users[admin]),
                    "status": "done",
                    "resolution": {"kind": "auskunft_erteilt"},
                },
                headers=self.h,
            )
        )
        _backdate(settings, tenant or world.tenant_a, self.ticket_id, days_ago)
        self.n = 1

    def reply(self, *, auto_submitted: str | None = None, msg_id: str | None = None) -> Any:
        self.n += 1
        raw = _eml(
            self.sender,
            f"Re: Fenster {self.tag}",
            msg_id or f"<fu-{self.tag}-{self.n}-{RUN}@x>",
            in_reply_to=self.first_id,
            auto_submitted=auto_submitted,
        )
        return _ingest(self.client, self.h, raw, self.box["id"])

    def detail(self, ticket_id: str | None = None) -> Any:
        return _ok(self.client.get(f"{T}/{ticket_id or self.ticket_id}", headers=self.h))


def _kinds(detail: dict[str, Any]) -> list[str]:
    return [e["kind"] for e in detail["events"]]


def test_closed_10_days_ago_reopens(client: TestClient, settings: Any, world: World) -> None:
    case = Case(client, settings, world, "d10", 10)
    msg = case.reply()
    assert msg["ticket_id"] == case.ticket_id
    detail = case.detail()
    assert detail["status"] == "in_progress"
    assert detail["resolved_at"] is None
    assert _kinds(detail).count("reopened") == 1
    assert detail["follow_ups"] == []
    assert detail["follow_up_of"] is None


def test_closed_40_days_ago_creates_follow_up_with_link_and_preset(
    client: TestClient, settings: Any, world: World
) -> None:
    case = Case(client, settings, world, "d40", 40)
    h = case.h
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "940",
                "name": f"Objekt Folge {RUN}",
                "management_type": "rental",
                "street": "Hauptstraße",
                "house_number": "7",
                "postal_code": "40789",
                "city": "Monheim",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building["id"],
                "number": "3",
                "label": "WE 3",
                "unit_type": "apartment",
            },
            headers=h,
        ),
        201,
    )
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Frieda", "last_name": f"Folge{RUN}"},
            headers=h,
        ),
        201,
    )
    # Die Zuordnung am abgeschlossenen Ticket, die das Folgeticket übernehmen soll.
    _ok(
        client.patch(
            f"{T}/{case.ticket_id}",
            json={"property_id": prop["id"], "unit_id": unit["id"], "contact_id": contact["id"]},
            headers=h,
        )
    )
    _backdate(settings, world.tenant_a, case.ticket_id, 40)

    msg = case.reply(msg_id=f"<fu-d40-reply-{RUN}@x>")
    new_id = str(msg["ticket_id"])
    assert new_id != case.ticket_id

    old = case.detail()
    assert old["status"] == "done"  # bleibt abgeschlossen
    assert old["resolved_at"] is not None
    assert "reopened" not in _kinds(old)
    assert "follow_up_created" in _kinds(old)
    assert [f["id"] for f in old["follow_ups"]] == [new_id]
    assert any(
        c["internal"] and c["body"].startswith("Neuer Folgevorgang #") for c in old["comments"]
    ), old["comments"]

    new = case.detail(new_id)
    assert new["follow_up_of_ticket_id"] == case.ticket_id
    assert new["follow_up_of"]["id"] == case.ticket_id
    assert new["follow_up_of"]["number"] == case.number
    assert new["property_id"] == prop["id"]
    assert new["unit_id"] == unit["id"]
    assert new["contact_id"] == contact["id"]
    assert new["status"] == "new"
    assert new["source"] == "email"
    assert {"follow_up_of", "mail_received"} <= set(_kinds(new))
    note = next(c for c in new["comments"] if c["body"].startswith("Folgevorgang zu Ticket"))
    assert note["internal"] is True
    assert f"#{case.number}" in note["body"]
    assert "30 Tagen" in note["body"]
    thread = _ok(client.get(f"{T}/{new_id}/messages", headers=h))
    assert [m["id"] for m in thread] == [msg["id"]]

    # Bearbeiter des Vorgängers erfährt vom Folgevorgang.
    notes = _ok(client.get("/api/v1/workspace/notifications", headers=h))
    items = notes if isinstance(notes, list) else notes.get("items", [])
    assert any(
        n["kind"] == "ticket.follow_up_created" and f"#{case.number}" in n["title"] for n in items
    ), items

    # Idempotenz: dieselbe Mail ein zweites Mal verarbeitet ergibt kein zweites Folgeticket.
    again = case.reply(msg_id=f"<fu-d40-reply-{RUN}@x>")
    assert again["id"] == msg["id"]
    assert again["ticket_id"] == new_id
    assert [f["id"] for f in case.detail()["follow_ups"]] == [new_id]

    # Eine weitere Mail im alten Thread landet am offenen Folgeticket, nicht an einem dritten.
    later = case.reply()
    assert later["ticket_id"] == new_id
    assert len(case.detail()["follow_ups"]) == 1
    assert _kinds(case.detail(new_id)).count("mail_received") == 2


def test_boundary_exactly_30_days_reopens_31_days_follows_up(
    client: TestClient, settings: Any, world: World
) -> None:
    at30 = Case(client, settings, world, "d30", 30)
    assert at30.reply()["ticket_id"] == at30.ticket_id
    assert at30.detail()["status"] == "in_progress"

    at31 = Case(client, settings, world, "d31", 31)
    msg = at31.reply()
    assert msg["ticket_id"] != at31.ticket_id
    assert at31.detail()["status"] == "done"
    assert at31.detail(str(msg["ticket_id"]))["follow_up_of"]["id"] == at31.ticket_id


def test_tenant_setting_overrides_window(client: TestClient, settings: Any, world: World) -> None:
    admin = bearer(login(client, world, "tfuadmin"))
    reader = bearer(login(client, world, "tfureader"))
    assert _ok(client.get(SETTINGS, headers=admin))["ticket_reopen_window_days"] == 30
    # Validierung und Berechtigung.
    for bad in (-1, 3651):
        assert (
            client.patch(
                SETTINGS, json={"ticket_reopen_window_days": bad}, headers=admin
            ).status_code
            == 422
        )
    assert (
        client.patch(SETTINGS, json={"ticket_reopen_window_days": 5}, headers=reader).status_code
        == 403
    )
    try:
        out = _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 5}, headers=admin))
        assert out["ticket_reopen_window_days"] == 5
        short = Case(client, settings, world, "w5", 10)
        msg = short.reply()
        assert msg["ticket_id"] != short.ticket_id
        note = next(
            c
            for c in short.detail(str(msg["ticket_id"]))["comments"]
            if c["body"].startswith("Folgevorgang zu Ticket")
        )
        assert "5 Tagen" in note["body"]

        _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 60}, headers=admin))
        long = Case(client, settings, world, "w60", 40)
        assert long.reply()["ticket_id"] == long.ticket_id
        assert long.detail()["status"] == "in_progress"

        # 0: jede neue Mail an ein abgeschlossenes Ticket wird ein Folgevorgang.
        _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 0}, headers=admin))
        today = Case(client, settings, world, "w0", 0)
        assert today.reply()["ticket_id"] == today.ticket_id  # heute geschlossen: 0 Tage
        yesterday = Case(client, settings, world, "w0y", 1)
        assert yesterday.reply()["ticket_id"] != yesterday.ticket_id
    finally:
        _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 30}, headers=admin))


def test_auto_reply_neither_reopens_nor_creates_follow_up(
    client: TestClient, settings: Any, world: World
) -> None:
    old = Case(client, settings, world, "ar40", 40)
    msg = old.reply(auto_submitted="auto-replied")
    assert msg["ticket_id"] == old.ticket_id  # am alten Ticket abgelegt, nachvollziehbar
    detail = old.detail()
    assert detail["status"] == "done"
    assert detail["follow_ups"] == []
    received = [e for e in detail["events"] if e["kind"] == "mail_received"]
    assert received[-1]["data"].get("auto_reply") is True

    recent = Case(client, settings, world, "ar10", 10)
    assert recent.reply(auto_submitted="auto-generated")["ticket_id"] == recent.ticket_id
    assert recent.detail()["status"] == "done"
    assert "reopened" not in _kinds(recent.detail())

    # "Auto-Submitted: no" ist eine normale Mail und öffnet wieder.
    assert recent.reply(auto_submitted="no")["ticket_id"] == recent.ticket_id
    assert recent.detail()["status"] == "in_progress"


def test_tenant_separation(client: TestClient, settings: Any, world: World) -> None:
    admin_a = bearer(login(client, world, "tfuadmin"))
    case = Case(client, settings, world, "sep", 40)
    admin_b = bearer(login(client, world, "tfuotherb"))
    # Einstellung wirkt nur im eigenen Mandanten.
    try:
        _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 90}, headers=admin_b))
        assert _ok(client.get(SETTINGS, headers=admin_a))["ticket_reopen_window_days"] == 30
        # Mandant B erhält eine Mail mit der Ticketkennung aus A: kein Zugriff auf A.
        box_b = _mailbox(client, admin_b, f"info-fu-b-{RUN}@example.com")
        raw = _eml(case.sender, f"Re: Fenster TNR#{case.number}", f"<fu-sep-b-{RUN}@x>")
        msg_b = _ingest(client, admin_b, raw, box_b["id"])
        assert msg_b["ticket_id"] != case.ticket_id
        assert client.get(f"{T}/{case.ticket_id}", headers=admin_b).status_code == 404
        # In A greift das Fenster von A (30 Tage), nicht das von B (90 Tage).
        msg_a = case.reply()
        assert msg_a["ticket_id"] != case.ticket_id
        detail = case.detail()
        assert detail["status"] == "done"
        assert [f["id"] for f in detail["follow_ups"]] == [msg_a["ticket_id"]]
        assert client.get(f"{T}/{msg_a['ticket_id']}", headers=admin_b).status_code == 404
    finally:
        _ok(client.patch(SETTINGS, json={"ticket_reopen_window_days": 30}, headers=admin_b))


# Review 1.40.2: follow-up merged back into its case -----------------------------------------


def _set_follow_up_of(
    settings: Any, tenant_id: uuid.UUID, ticket_id: str, predecessor_id: str
) -> None:
    """Link state of a merge made before the fix (the merge kept the link of the follow-up);
    through the RLS tenant scope like a request."""
    from sqlalchemy import update

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.tickets.models import Ticket

    async def _run() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                result = await session.execute(
                    update(Ticket)
                    .where(Ticket.id == uuid.UUID(ticket_id))
                    .values(follow_up_of_ticket_id=uuid.UUID(predecessor_id))
                )
                assert result.rowcount == 1  # type: ignore[attr-defined]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def _merge(case: Case, source: str, target: str) -> Any:
    return _ok(
        case.client.post(
            f"{T}/merge",
            json={"ticket_ids": [source], "target_ticket_id": target},
            headers=case.h,
        ),
        201,
    )


def _finish(case: Case, ticket_id: str, world: World) -> None:
    _ok(
        case.client.patch(
            f"{T}/{ticket_id}",
            json={
                "assignee_user_id": str(world.users["tfuadmin"]),
                "status": "done",
                "resolution": {"kind": "auskunft_erteilt"},
            },
            headers=case.h,
        )
    )


def test_follow_up_merged_back_into_predecessor_next_mails_are_ingested(
    client: TestClient, settings: Any, world: World
) -> None:
    """Probe of review 1.40.2: follow-up F merged back into its finished predecessor P, then
    further mails of the thread. Before the fix the resolution walked P, F, P and tried a
    second follow-up of P (uq_ticket_follow_up_of, HTTP 500, Gmail sync retried forever)."""
    case = Case(client, settings, world, "mb", 40)
    first = str(case.reply()["ticket_id"])
    assert first != case.ticket_id
    _merge(case, first, case.ticket_id)

    merged = case.detail(first)
    assert merged["merged_into_ticket_id"] == case.ticket_id
    # Zurückgeführt: die Verknüpfung ist gelöst, der Verlauf behält sie.
    assert merged["follow_up_of_ticket_id"] is None
    into = next(e for e in merged["events"] if e["kind"] == "merged_into")
    assert into["data"]["released_follow_up_of"] == case.ticket_id
    predecessor = case.detail()
    assert predecessor["status"] == "done"
    assert predecessor["follow_ups"] == []

    # Nächste Mail: eingelesen (kein 500), neuer Folgevorgang des weiterhin alten Vorgängers.
    new_id = str(case.reply()["ticket_id"])
    assert new_id not in {case.ticket_id, first}
    assert case.detail(new_id)["follow_up_of_ticket_id"] == case.ticket_id
    assert [f["id"] for f in case.detail()["follow_ups"]] == [new_id]
    assert case.detail()["status"] == "done"

    # Übernächste Mail: am offenen neuen Folgevorgang, kein weiteres Ticket.
    assert str(case.reply()["ticket_id"]) == new_id
    assert [f["id"] for f in case.detail()["follow_ups"]] == [new_id]
    assert _kinds(case.detail(new_id)).count("mail_received") == 2


def test_merged_back_link_of_older_merge_is_released_on_next_mail(
    client: TestClient, settings: Any, world: World
) -> None:
    """Rows merged before the fix still carry the link of the merged back follow-up: the next
    mail releases it and creates the new follow-up instead of failing on the unique index."""
    case = Case(client, settings, world, "mbl", 40)
    first = str(case.reply()["ticket_id"])
    _merge(case, first, case.ticket_id)
    _set_follow_up_of(settings, world.tenant_a, first, case.ticket_id)
    assert [f["id"] for f in case.detail()["follow_ups"]] == [first]

    new_id = str(case.reply()["ticket_id"])
    assert new_id not in {case.ticket_id, first}
    assert case.detail(first)["follow_up_of_ticket_id"] is None
    assert [f["id"] for f in case.detail()["follow_ups"]] == [new_id]
    created = next(
        e
        for e in case.detail()["events"]
        if e["kind"] == "follow_up_created" and e["data"]["ticket_id"] == new_id
    )
    assert created["data"]["released_follow_up"]["ticket_id"] == first
    assert str(case.reply()["ticket_id"]) == new_id


def test_predecessor_merged_into_follow_up_keeps_link_and_ingests(
    client: TestClient, settings: Any, world: World
) -> None:
    """Other direction: the finished predecessor P merged into its follow-up F. The link stays
    (F remains the follow-up of P), every mail of the case lands on F; once F is finished
    long ago, the next mail creates a follow-up of F."""
    case = Case(client, settings, world, "mbr", 40)
    follow = str(case.reply()["ticket_id"])
    _merge(case, case.ticket_id, follow)
    assert case.detail()["merged_into_ticket_id"] == follow
    assert case.detail(follow)["follow_up_of_ticket_id"] == case.ticket_id

    assert str(case.reply()["ticket_id"]) == follow
    assert str(case.reply()["ticket_id"]) == follow
    assert case.detail(follow)["status"] not in {"done", "closed", "rejected"}

    _finish(case, follow, world)
    _backdate(settings, world.tenant_a, follow, 40)
    later = str(case.reply()["ticket_id"])
    assert later not in {case.ticket_id, follow}
    assert case.detail(later)["follow_up_of_ticket_id"] == follow
    assert case.detail(follow)["status"] == "done"
    assert str(case.reply()["ticket_id"]) == later


def test_follow_up_of_follow_up_merged_back_into_first_ticket(
    client: TestClient, settings: Any, world: World
) -> None:
    """Chain P, F1, F2 with F2 merged back into P: the resolution stops at F1 (F2 is no
    successor any more), releases F2 and creates the follow-up of F1; nothing cycles."""
    case = Case(client, settings, world, "mbc", 40)
    f1 = str(case.reply()["ticket_id"])
    _finish(case, f1, world)
    _backdate(settings, world.tenant_a, f1, 40)
    f2 = str(case.reply()["ticket_id"])
    assert f2 not in {case.ticket_id, f1}
    assert case.detail(f2)["follow_up_of_ticket_id"] == f1
    _merge(case, f2, case.ticket_id)
    # Nicht der direkte Vorgänger: die Verknüpfung bleibt beim Zusammenführen bestehen.
    assert case.detail(f2)["follow_up_of_ticket_id"] == f1

    f3 = str(case.reply()["ticket_id"])
    assert f3 not in {case.ticket_id, f1, f2}
    assert case.detail(f3)["follow_up_of_ticket_id"] == f1
    assert case.detail(f2)["follow_up_of_ticket_id"] is None
    assert str(case.reply()["ticket_id"]) == f3
