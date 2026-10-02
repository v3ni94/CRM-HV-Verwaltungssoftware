"""P13 (Lückenliste 30.09.2026): portal chat at the ticket (M21-01), document status neu/gelesen
(M21-02, SA-06), damage location (M21-03), representatives with power of attorney (M21-05),
owner views (M21-06, M21-07, SA-05), statistics and feature switches (M21-08, SA-01), form
builder delivery (SA-03) and the consent bound support view (SA-02)."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok
from tests.integration.test_m21_portal_owner import _ownership, _portal_user, _weg

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p13a-{RUN}", name=f"P13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p13b-{RUN}", name=f"P13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = (
            ("p13admin", a, ["tenant_admin"]),
            ("p13adminb", b, ["tenant_admin"]),
            ("p13reader", a, ["read_only"]),
        )
        for name, tenant, roles in specs:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=roles, actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


@dataclass
class W:
    admin: dict[str, str]
    admin_b: dict[str, str]
    reader: dict[str, str]
    owner1: dict[str, str]
    owner1_contact: str
    owner1_account: str
    rep: dict[str, str]
    rep_account: str
    outsider: dict[str, str]
    outsider_account: str
    unit: str
    hoa: str
    weg_id: str


def _account_id(c: TestClient, h: dict[str, str], contact: str) -> str:
    return str(_ok(c.get(f"{PA}/accounts", params={"contact_id": contact}, headers=h))[0]["id"])


@pytest.fixture(scope="module")
def w(client: TestClient, world: World) -> W:
    c = client
    h = bearer(login(c, world, "p13admin"))
    weg, hoa = _weg(c, h, "913", "P13 WEG")
    unit1, unit2 = _unit(c, h, weg["id"], "01"), _unit(c, h, weg["id"], "02")
    o1_party, _ = _party(c, h, "P13Eig1")
    rep_party, _ = _party(c, h, "P13Vertreter")
    out_party, _ = _party(c, h, "P13Fremd")
    _ownership(c, h, unit1, o1_party)
    _ownership(c, h, unit2, rep_party)
    contacts = {
        n: _contact_of(c, h, p) for n, p in (("o", o1_party), ("r", rep_party), ("x", out_party))
    }
    owner1 = _portal_user(c, h, world, "p13owner1", contacts["o"])
    rep = _portal_user(c, h, world, "p13rep", contacts["r"])
    outsider = _portal_user(c, h, world, "p13out", contacts["x"])
    return W(
        admin=h,
        admin_b=bearer(login(c, world, "p13adminb")),
        reader=bearer(login(c, world, "p13reader")),
        owner1=owner1,
        owner1_contact=contacts["o"],
        owner1_account=_account_id(c, h, contacts["o"]),
        rep=rep,
        rep_account=_account_id(c, h, contacts["r"]),
        outsider=outsider,
        outsider_account=_account_id(c, h, contacts["x"]),
        unit=unit1,
        hoa=hoa,
        weg_id=weg["id"],
    )


def _upload(c: TestClient, h: dict[str, str], name: str = "a.pdf") -> str:
    return str(
        _ok(
            c.post(
                f"{P}/uploads", files={"file": (name, b"%PDF-1.4 x", "application/pdf")}, headers=h
            ),
            201,
        )["id"]
    )


# Feature switches and statistics ----------------------------------------------------------


def test_features_default_off_and_permissions(client: TestClient, w: W) -> None:
    c = client
    assert _ok(c.get(f"{PA}/features", headers=w.admin)) == {
        "chat_enabled": False,
        "chat_ai_prequalification_enabled": False,
        "support_login_enabled": False,
        "owner_rental_income_enabled": False,
        "owner_ticket_scope": "released",
        "chat_bot_enabled": False,
        "privacy_feature_enabled": False,
        "provider_rating_display": "off",
        "owner_rental_statements_enabled": False,
        "tenant_statement_enabled": False,
        "portal_owner_receipts_enabled": False,
        "owner_hoa_rental_statements_enabled": False,
    }
    assert (
        c.patch(f"{PA}/features", json={"chat_enabled": True}, headers=w.reader).status_code == 403
    )
    assert c.patch(f"{PA}/features", json={"bogus": True}, headers=w.admin).status_code == 422
    # Tenant B has its own switches.
    assert _ok(c.get(f"{PA}/features", headers=w.admin_b))["chat_enabled"] is False
    me = _ok(c.get(f"{P}/me", headers=w.owner1))
    assert me["features"]["chat_enabled"] is False
    assert me["representations"] == []


def test_statistics_counts_accounts(client: TestClient, w: W) -> None:
    stats = _ok(client.get(f"{PA}/statistics", headers=w.admin))
    assert stats["accounts"]["active"] >= 3
    assert stats["accounts"]["total"] >= stats["accounts"]["active"]
    assert stats["period_days"] == 30
    assert client.get(f"{PA}/statistics", headers=w.owner1).status_code == 403
    other = _ok(client.get(f"{PA}/statistics", headers=w.admin_b))
    assert other["accounts"]["total"] == 0


# Chat -------------------------------------------------------------------------------------


def test_chat_locked_then_thread_and_reply(client: TestClient, w: W) -> None:
    c = client
    ticket = _ok(
        c.post(
            f"{P}/tickets",
            json={"title": "Heizung kalt", "description": "Seit gestern", "location": "Bad, 2. OG"},
            headers=w.owner1,
        ),
        201,
    )
    tid = ticket["id"]
    # M21-03: the location is part of the public description of the ticket.
    detail = _ok(c.get(f"/api/v1/tickets/{tid}", headers=w.admin))
    assert "Standort: Bad, 2. OG" in (detail.get("public_description") or "")
    # Locked while the switch is off.
    assert c.get(f"{P}/tickets/{tid}/messages", headers=w.owner1).status_code == 403
    assert (
        c.post(f"{P}/tickets/{tid}/messages", json={"body": "Hallo"}, headers=w.owner1).status_code
        == 403
    )
    _ok(c.patch(f"{PA}/features", json={"chat_enabled": True}, headers=w.admin))
    assert _ok(c.get(f"{P}/tickets/{tid}/messages", headers=w.owner1)) == []
    sent = _ok(
        c.post(f"{P}/tickets/{tid}/messages", json={"body": "Hallo Verwaltung"}, headers=w.owner1),
        201,
    )
    assert sent["direction"] == "own"
    assert (
        c.post(f"{P}/tickets/{tid}/messages", json={"body": ""}, headers=w.owner1).status_code
        == 422
    )
    # CRM reply reaches the portal user and creates a notification.
    reply = _ok(
        c.post(f"{PA}/tickets/{tid}/messages", json={"body": "Wir melden uns"}, headers=w.admin),
        201,
    )
    assert reply["notified"] is True
    thread = _ok(c.get(f"{P}/tickets/{tid}/messages", headers=w.owner1))
    assert [m["direction"] for m in thread] == ["own", "management"]
    notes = _ok(c.get(f"{P}/notifications", headers=w.owner1))
    assert any("Antwort der Verwaltung" in n["title"] for n in notes)
    # Internal comments never show up in the portal.
    _ok(
        c.post(
            f"/api/v1/tickets/{tid}/comments",
            json={"body": "intern", "internal": True},
            headers=w.admin,
        ),
        201,
    )
    assert len(_ok(c.get(f"{P}/tickets/{tid}/messages", headers=w.owner1))) == 2
    # Somebody else's ticket is 404, the reader may not reply, tenant B sees nothing.
    assert c.get(f"{P}/tickets/{tid}/messages", headers=w.outsider).status_code == 404
    assert (
        c.post(f"{PA}/tickets/{tid}/messages", json={"body": "x"}, headers=w.reader).status_code
        == 403
    )
    assert (
        c.post(f"{PA}/tickets/{tid}/messages", json={"body": "x"}, headers=w.admin_b).status_code
        == 403
    )


def test_prequalification_is_proposal_and_ai_stays_locked(client: TestClient, w: W) -> None:
    c = client
    tid = _ok(
        c.post(
            f"{P}/tickets", json={"title": "Wasser", "description": "Rohrbruch"}, headers=w.owner1
        ),
        201,
    )["id"]
    out = _ok(
        c.post(
            f"{P}/tickets/{tid}/prequalify",
            json={"text": "Rohrbruch im Keller, Wasser läuft"},
            headers=w.owner1,
        )
    )
    assert out["urgent_hint"] is True
    assert out["source"] == "regelbasiert"
    assert out["ai_available"] is False
    assert "nicht eingeschaltet" in out["ai_blocked_reason"]
    _ok(c.patch(f"{PA}/features", json={"chat_ai_prequalification_enabled": True}, headers=w.admin))
    out = _ok(
        c.post(f"{P}/tickets/{tid}/prequalify", json={"text": "Aufzug defekt"}, headers=w.owner1)
    )
    # No released provider with data processing agreement in the test tenant: still blocked.
    assert out["ai_available"] is False
    assert out["ai_blocked_reason"]
    # Switching the chat off also switches the AI stage off.
    feats = _ok(c.patch(f"{PA}/features", json={"chat_enabled": False}, headers=w.admin))
    assert feats["chat_ai_prequalification_enabled"] is False
    _ok(c.patch(f"{PA}/features", json={"chat_enabled": True}, headers=w.admin))


# Documents neu/gelesen --------------------------------------------------------------------


def test_document_list_shows_new_then_read(client: TestClient, w: W) -> None:
    c = client
    doc = _upload(c, w.owner1)
    row = next(d for d in _ok(c.get(f"{P}/documents", headers=w.owner1)) if d["id"] == doc)
    assert row["is_new"] is True
    assert row["last_opened_at"] is None
    _ok(c.get(f"{P}/documents/{doc}", headers=w.owner1))
    row = next(d for d in _ok(c.get(f"{P}/documents", headers=w.owner1)) if d["id"] == doc)
    assert row["is_new"] is False
    assert row["last_opened_at"] is not None
    # Listing alone wrote nothing; another user's state is independent.
    assert all(d["id"] != doc for d in _ok(c.get(f"{P}/documents", headers=w.outsider)))


# Representatives --------------------------------------------------------------------------


def test_representative_sees_owner_view_only_within_period(client: TestClient, w: W) -> None:
    c = client
    # Before the power of attorney the representative owns unit 02 only.
    hoa_before = _ok(c.get(f"{P}/hoa-account", headers=w.rep))
    assert len(hoa_before["contracts"]) == 1
    doc = _upload(c, w.owner1, "vollmacht.pdf")
    body = {
        "account_id": w.rep_account,
        "principal_contact_id": w.owner1_contact,
        "document_id": doc,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
    }
    assert c.post(f"{PA}/representations", json=body, headers=w.reader).status_code == 403
    assert (
        c.post(f"{PA}/representations", json={**body, "valid_to": "2025-01-01"}, headers=w.admin)
    ).status_code == 422
    assert (
        c.post(
            f"{PA}/representations",
            json={**body, "principal_contact_id": w.owner1_contact, "account_id": w.owner1_account},
            headers=w.admin,
        )
    ).status_code == 422
    assert c.post(f"{PA}/representations", json=body, headers=w.admin_b).status_code in (403, 404)
    rep = _ok(c.post(f"{PA}/representations", json=body, headers=w.admin), 201)
    assert rep["status"] == "active"
    after = _ok(c.get(f"{P}/hoa-account", headers=w.rep))
    assert len(after["contracts"]) == 2
    me = _ok(c.get(f"{P}/me", headers=w.rep))
    assert [r["principal_contact_id"] for r in me["representations"]] == [w.owner1_contact]
    # U05 (M21-05): own role "representative", principal name and period in the portal.
    assert "representative" in me["portal_roles"]
    assert me["representations"][0]["principal_name"]
    own = _ok(c.get(f"{P}/representations", headers=w.rep))["items"]
    assert [(r["state"], r["valid_to"]) for r in own] == [("active", "2026-12-31")]
    assert c.get(f"{P}/representations", headers=w.owner1).json()["items"] == []
    # Revoking ends the access at once.
    revoked = _ok(c.post(f"{PA}/representations/{rep['id']}/revoke", headers=w.admin))
    assert revoked["status"] == "revoked"
    assert len(_ok(c.get(f"{P}/hoa-account", headers=w.rep))["contracts"]) == 1
    me_after = _ok(c.get(f"{P}/me", headers=w.rep))
    assert "representative" not in me_after["portal_roles"]
    assert [r["state"] for r in _ok(c.get(f"{P}/representations", headers=w.rep))["items"]] == [
        "revoked"
    ]
    listing = _ok(
        c.get(f"{PA}/representations", params={"account_id": w.rep_account}, headers=w.admin)
    )
    assert [r["status"] for r in listing] == ["revoked"]
    # Q05 (M21-05): the list names the representative (contact and login address) for the CRM.
    assert listing[0]["representative_contact_id"] is not None
    assert "@" in listing[0]["representative_email"]
    assert _ok(c.get(f"{PA}/representations", headers=w.admin_b)) == []


def test_expired_representation_loses_access(client: TestClient, w: W) -> None:
    c = client
    doc = _upload(c, w.owner1, "vollmacht-alt.pdf")
    body = {
        "account_id": w.rep_account,
        "principal_contact_id": w.owner1_contact,
        "document_id": doc,
        "valid_from": "2025-01-01",
        "valid_to": "2025-06-30",
    }
    _ok(c.post(f"{PA}/representations", json=body, headers=w.admin), 201)
    assert len(_ok(c.get(f"{P}/hoa-account", headers=w.rep))["contracts"]) == 1
    me = _ok(c.get(f"{P}/me", headers=w.rep))
    assert me["representations"] == []
    assert "representative" not in me["portal_roles"]
    own = _ok(c.get(f"{P}/representations", headers=w.rep))["items"]
    expired = [r for r in own if r["valid_to"] == "2025-06-30"]
    assert [r["state"] for r in expired] == ["expired"]
    assert expired[0]["expires_in_days"] is None
    assert all(r["state"] != "active" for r in own)


# Owner views ------------------------------------------------------------------------------


def test_owner_views_scope_and_locks(client: TestClient, w: W) -> None:
    c = client
    for path in ("tickets", "payment-resolutions", "consumption-info"):
        assert c.get(f"{P}/owner/{path}", headers=w.outsider).status_code == 403, path
    # Tickets only when released for owners.
    own = _ok(
        c.post(
            f"{P}/tickets", json={"title": "Dach undicht", "description": "Flur"}, headers=w.owner1
        ),
        201,
    )
    assert _ok(c.get(f"{P}/owner/tickets", headers=w.owner1)) == []
    # Payment resolutions: only announced resolutions on plan or levy.
    for subject_type, subject in (("special_levy", "Sonderumlage Dach"), ("other", "Hausordnung")):
        _ok(
            c.post(
                "/api/v1/hoa/resolutions",
                json={
                    "legal_entity_id": w.hoa,
                    "decided_on": "2026-05-15",
                    "subject": subject,
                    "wording": f"Beschluss {subject}",
                    "status": "final",
                    "kind": "external",
                    "subject_type": subject_type,
                },
                headers=w.admin,
            ),
            201,
        )
    pay = _ok(c.get(f"{P}/owner/payment-resolutions", headers=w.owner1))
    assert [i["subject"] for i in pay["items"]] == ["Sonderumlage Dach"]
    assert pay["items"][0]["kind"] == "special_levy"
    assert "keine Zahlung" in pay["note"]
    # Consumption information is locked until the tenant switches are on (rule H03).
    assert c.get(f"{P}/owner/consumption-info", headers=w.owner1).status_code == 403
    assert own["number"]


# Forms ------------------------------------------------------------------------------------


def test_form_builder_new_types_and_delivery(client: TestClient, w: W) -> None:
    c = client
    fields = [
        {"key": "h", "label": "Angaben", "type": "heading"},
        {"key": "zeit", "label": "Uhrzeit", "type": "time", "required": True},
        {"key": "mehr", "label": "Mehrfach", "type": "multiselect", "options": ["a", "b"]},
        {"key": "ok", "label": "Einverstanden", "type": "checkbox", "required": True},
        {"key": "mail", "label": "E-Mail", "type": "email"},
    ]
    bad = c.post(
        f"{PA}/forms",
        json={"name": "F", "category": "Antrag", "fields": fields, "delivery": "email"},
        headers=w.admin,
    )
    assert bad.status_code == 422
    assert {e["field"] for e in bad.json()["errors"]} == {"delivery_email"}
    tpl = _ok(
        c.post(
            f"{PA}/forms",
            json={
                "name": "Terminwunsch",
                "category": "Antrag",
                "fields": fields,
                "delivery": "email",
                "delivery_email": "verwaltung@example.org",
            },
            headers=w.admin,
        ),
        201,
    )
    assert tpl["delivery"] == "email"
    assert tpl["delivery_email"] == "verwaltung@example.org"
    visible = _ok(c.get(f"{P}/forms", headers=w.owner1))
    shown = next(t for t in visible if t["id"] == tpl["id"])
    assert "delivery_email" not in shown
    bad_values = c.post(
        f"{P}/forms/{tpl['id']}/submissions",
        json={"values": {"zeit": "25:99", "ok": False}},
        headers=w.owner1,
    )
    assert bad_values.status_code == 422
    done = _ok(
        c.post(
            f"{P}/forms/{tpl['id']}/submissions",
            json={"values": {"zeit": "08:30", "mehr": ["a", "b"], "ok": True}},
            headers=w.owner1,
        ),
        201,
    )
    # The ticket exists as record; no mailbox is set up in the test tenant, so sending failed
    # and the portal user is told neutrally (no error text).
    assert done["delivery"] == "email"
    assert done["delivery_failed"] is True
    ticket = _ok(c.get(f"/api/v1/tickets/{done['ticket_id']}", headers=w.admin))
    text = ticket["public_description"]
    assert "Uhrzeit: 08:30" in text
    assert "Mehrfach: a, b" in text
    assert "Einverstanden: ja" in text
    assert "Angaben" not in text
    patched = _ok(c.patch(f"{PA}/forms/{tpl['id']}", json={"delivery": "ticket"}, headers=w.admin))
    assert patched["delivery"] == "ticket"
    assert patched["delivery_email"] is None


# Support view -----------------------------------------------------------------------------


def test_support_view_needs_switch_consent_and_is_logged(client: TestClient, w: W) -> None:
    c = client
    url = f"{PA}/accounts/{w.owner1_account}/support-view"
    params = {"reason": "Rückfrage zur Meldung"}
    assert c.get(url, params=params, headers=w.admin).status_code == 403  # switch off
    assert c.post(f"{P}/support-consent", json={}, headers=w.owner1).status_code == 403
    _ok(c.patch(f"{PA}/features", json={"support_login_enabled": True}, headers=w.admin))
    assert c.get(url, params=params, headers=w.admin).status_code == 403  # no consent
    assert _ok(c.get(f"{P}/support-consent", headers=w.owner1))["active"] is False
    assert c.post(f"{P}/support-consent", json={"hours": 500}, headers=w.owner1).status_code == 422
    _ok(c.post(f"{P}/support-consent", json={"hours": 2}, headers=w.owner1), 201)
    assert c.get(url, params={"reason": "x"}, headers=w.admin).status_code == 422
    assert c.get(url, params=params, headers=w.reader).status_code == 403
    assert c.get(url, params=params, headers=w.admin_b).status_code == 403
    view = _ok(c.get(url, params=params, headers=w.admin))
    assert view["read_only"] is True
    assert "owner" in view["roles"]
    log = _ok(c.get(f"{PA}/accounts/{w.owner1_account}/support-log", headers=w.admin))
    assert len(log) == 1
    assert log[0]["reason"] == "Rückfrage zur Meldung"
    # Revoking the consent closes the view again; the log stays.
    assert c.delete(f"{P}/support-consent", headers=w.owner1).status_code == 204
    assert c.get(url, params=params, headers=w.admin).status_code == 403
    assert len(_ok(c.get(f"{PA}/accounts/{w.owner1_account}/support-log", headers=w.admin))) == 1
    # A different account has no consent at all.
    other = f"{PA}/accounts/{w.outsider_account}/support-view"
    assert c.get(other, params=params, headers=w.admin).status_code == 403
