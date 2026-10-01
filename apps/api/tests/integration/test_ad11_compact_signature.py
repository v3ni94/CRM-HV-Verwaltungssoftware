"""Kurz senden signiert mit dem handelnden Nutzer (AD11, Betreiber 01.10.2026).

Zwei Nutzer desselben Mandanten antworten kurz auf dieselbe Eingangsmail: der gespeicherte
Text enthält jeweils genau einmal den eigenen Namen, die eigene Position und den Firmennamen,
nie die Daten des anderen. Ein Vorschlag mit eigener Grußformel samt fremdem Namen und Firma
wird bereinigt. Einreichen signiert nicht doppelt. Beim Einzelunternehmen entfällt die
Funktionsbezeichnung; ohne Position meldet die Vorschau ``position_missing``."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _upload
from tests.integration.test_m20_mail_approval import _eml

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
S = "/api/v1/mail/signature"
INA = f"Ina Brink {RUN}"
TIMO = f"Timo Geschäft {RUN}"
HVM = {
    "name": "Hausverwaltung Müller GmbH",
    "legal_form": "GmbH",
    "street": "Musterstraße 1",
    "postal_code": "40000",
    "city": "Musterstadt",
}
SOLE = {"name": "Timo Müller", "legal_form": "Einzelunternehmen", "city": "Musterstadt"}


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ad11a-{RUN}", name=f"AD11A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ad11b-{RUN}", name=f"AD11B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "ad11ina": (INA, [(a, "tenant_admin")]),
            "ad11timo": (TIMO, [(a, "tenant_admin")]),
            "ad11sole": (f"Timo Sole {RUN}", [(b, "tenant_admin")]),
            "ad11nopos": (f"Ohne Position {RUN}", [(a, "tenant_admin")]),
        }
        for name, (display, memberships) in specs.items():
            uid = await services.create_user(
                factory, email=world.email(name), display_name=display, password=PASSWORD
            )
            world.users[name] = uid
            for tenant, role in memberships:
                await services.add_member(
                    factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
                )
        return world
    finally:
        await engine.dispose()


def _company(database: Database, tenant: Any, company: dict[str, Any]) -> None:
    engine = sa.create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)}
            )
            conn.execute(
                sa.text(
                    "UPDATE tenant_settings SET company = CAST(:c AS jsonb), "
                    "signature_template = '{}'::jsonb WHERE tenant_id = :t"
                ),
                {"c": json.dumps(company), "t": str(tenant)},
            )
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    built = asyncio.run(_world(_settings(database, redis_url)))
    _company(database, built.tenant_a, HVM)
    _company(database, built.tenant_b, SOLE)
    return built


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _inbound(client: TestClient, h: dict[str, str], tag: str) -> dict[str, Any]:
    box = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": f"box-{tag}@example.com", "kind": "imap"}, headers=h
        ),
        201,
    )
    doc = _upload(client, h, "mail.eml", _eml(f"m-{tag}@example.com", f"Frage {tag}", f"<{tag}@x>"))
    msg: dict[str, Any] = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    return msg


def _quick_send(client: TestClient, h: dict[str, str], message_id: str, text: str) -> str:
    """Same calls as CompactView "Kurz senden": POST reply-draft with the text, POST submit."""
    draft = _ok(
        client.post(f"{M}/messages/{message_id}/reply-draft", json={"body": text}, headers=h), 201
    )
    submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    assert submitted["status"] == "pending"
    assert submitted["body"] == draft["body"]  # idempotent: no second signature at submit
    return str(submitted["body"])


# AI-like proposal with its own closing block naming the other user and the company.
PROPOSAL = (
    "Sehr geehrte Damen und Herren,\n\nwir kümmern uns um die Heizung.\n\n"
    "Mit freundlichen Grüßen\n{other}\nHausverwaltung Müller GmbH\n[Name]\n[Firma]"
)


def test_two_users_quick_send_with_their_own_signature(client: TestClient, world: World) -> None:
    ina = bearer(login(client, world, "ad11ina"))
    timo = bearer(login(client, world, "ad11timo"))
    _ok(client.put(f"{S}/profile", json={"position": "Assistenz", "phone": None}, headers=ina))
    _ok(
        client.put(
            f"{S}/profile", json={"position": "Geschäftsführer", "phone": None}, headers=timo
        )
    )
    msg = _inbound(client, ina, f"ad11two-{RUN}")

    preview = _ok(client.get(f"{S}/preview", headers=ina))
    assert preview["text"].startswith(f"-- \n{INA}\nAssistenz\nHausverwaltung Müller GmbH\n")
    assert preview["position_missing"] is False

    body_ina = _quick_send(client, ina, msg["id"], PROPOSAL.format(other=TIMO))
    body_timo = _quick_send(client, timo, msg["id"], PROPOSAL.format(other=INA))
    for body, own, pos, other, other_pos in (
        (body_ina, INA, "Assistenz", TIMO, "Geschäftsführer"),
        (body_timo, TIMO, "Geschäftsführer", INA, "Assistenz"),
    ):
        assert body.count(own) == 1, body
        assert body.count(pos) == 1, body
        assert body.count("Hausverwaltung Müller GmbH") == 1, body
        assert other not in body
        assert other_pos not in body
        assert "[Name]" not in body
        assert "[Firma]" not in body
        assert body.count("\n-- \n") == 1
        assert f"Mit freundlichen Grüßen\n\n-- \n{own}\n{pos}\nHausverwaltung Müller GmbH\n" in body

    # Kurz senden again on the same draft (reused own draft): still one signature.
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=ina), 201)
    assert draft["body"].count("\n-- \n") <= 1


def test_missing_position_hint_and_signature_without_position(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ad11nopos"))
    preview = _ok(client.get(f"{S}/preview", headers=h))
    assert preview["position_missing"] is True
    msg = _inbound(client, h, f"ad11nopos-{RUN}")
    body = _quick_send(client, h, msg["id"], "Guten Tag,\n\ndanke.\n\nViele Grüße\n[Name]")
    assert f"Viele Grüße\n\n-- \nOhne Position {RUN}\nHausverwaltung Müller GmbH\n" in body


def test_sole_proprietorship_without_position(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ad11sole"))
    _ok(client.put(f"{S}/profile", json={"position": "Geschäftsführer", "phone": None}, headers=h))
    preview = _ok(client.get(f"{S}/preview", headers=h))
    assert preview["position_missing"] is False
    assert "Geschäftsführer" not in preview["text"]
    msg = _inbound(client, h, f"ad11sole-{RUN}")
    body = _quick_send(
        client, h, msg["id"], "Guten Tag,\n\ndanke.\n\nMit freundlichen Grüßen\nTimo Müller"
    )
    assert "Geschäftsführer" not in body
    assert body.count("Timo Müller") == 1, body
    assert f"Timo Sole {RUN}" in body
