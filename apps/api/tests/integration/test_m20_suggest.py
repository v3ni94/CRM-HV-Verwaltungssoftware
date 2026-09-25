"""M20 Übernahme: KI-Vorschlag je eingehender Mail und Playbooks aus geschlossenen Tickets.
Kein freigegebener Anbieter -> ``skipped``; mit gefaktem Anbieter -> Vorschlag inkl. lokaler
Playbook-Zuordnung per Schlagwort; ``apply-playbook`` liefert einen Entwurf und zählt
``usage_count``; Schließen eines Tickets lernt einen Playbook-Entwurf; Nur-Lese-Rolle scheitert
an den Schreibendpunkten mit 403."""

import asyncio
import json
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.ai.providers import Completion
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"

PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "small": {
            "model": "claude-haiku-4-5",
            "input_eur_per_mtok": "1",
            "output_eur_per_mtok": "5",
        },
        "large": {"model": "claude-opus-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


def _eml(sender: str, subject: str, msg_id: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    return bytes(msg)


class FakeProvider:
    def __init__(self) -> None:
        self.queue: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = self.queue.pop(0) if self.queue else {}
        return Completion(
            data=data,
            raw_text=json.dumps(data),
            tokens_in=100,
            tokens_out=50,
            model=kwargs["model"],
        )


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"sg-{RUN}", name=f"Suggest {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("sgadmin", "tenant_admin"),
            ("sgsecond", "tenant_admin"),
            ("sgreader", "read_only"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(
        _world(_settings(database, redis_url).model_copy(update={"ai_inline": True}))
    )


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url).model_copy(update={"ai_inline": True})
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _setup_provider(c: TestClient, admin: dict[str, str], second: dict[str, str]) -> None:
    dpa = _upload(c, admin, "avv.eml", b"Auftragsverarbeitungsvertrag Muster")
    body = {**PROVIDER, "dpa_document_id": dpa}
    _ok(c.put("/api/v1/ai/providers/anthropic", json=body, headers=admin), 200)
    _ok(c.post("/api/v1/ai/providers/anthropic/release", headers=second), 200)


def test_suggestion_skipped_without_provider(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "sgadmin"))
    raw = _eml(
        f"mieter{RUN}@example.com",
        f"Heizung defekt {RUN}",
        f"<sg1-{RUN}@x>",
        "Die Heizung ist kalt.",
    )
    doc = _upload(client, h, "m1.eml", raw)
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "auto_ticket": True}, headers=h), 201
    )
    assert msg["suggestion_status"] == "skipped"
    assert msg["suggestion"].get("reason")


def test_suggestion_ready_with_playbook_match(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    admin = bearer(login(client, world, "sgadmin"))
    second = bearer(login(client, world, "sgsecond"))
    _setup_provider(client, admin, second)

    playbook = _ok(
        client.post(
            f"{M}/playbooks",
            json={
                "title": f"Heizungsausfall {RUN}",
                "category": "Heizung",
                "keywords": ["heizung", "kalt", "keller"],
                "summary": "Heizungsausfall melden und Notdienst beauftragen.",
                "steps": ["Notdienst kontaktieren", "Mieter informieren"],
                "reply_template": "{anrede},\n\nwir kümmern uns um {ticket} bei Objekt {objekt}.",
                "status": "active",
            },
            headers=admin,
        ),
        201,
    )

    fake.queue.append(
        {
            "category": "Heizung",
            "urgency": "high",
            "summary": "Mieter meldet Heizungsausfall.",
            "property_number": "042",
            "contact_name": "Max Muster",
            "reply_draft": "Sehr geehrter Herr Muster, wir kümmern uns umgehend.",
        }
    )
    raw = _eml(
        f"mieter2{RUN}@example.com",
        f"Heizung defekt Objekt 042 {RUN}",
        f"<sg2-{RUN}@x>",
        "Seit heute Morgen ist die Heizung im Keller kalt.",
    )
    doc = _upload(client, admin, "m2.eml", raw)
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "auto_ticket": True}, headers=admin),
        201,
    )
    assert msg["suggestion_status"] == "ready"
    assert msg["suggestion"]["category"] == "Heizung"
    assert msg["suggestion"]["urgency"] == "high"
    assert msg["suggestion"]["playbook_id"] == playbook["id"]
    assert msg["suggestion"]["playbook_score"] >= 0.3

    applied = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/apply-playbook",
            json={"playbook_id": playbook["id"]},
            headers=admin,
        ),
        201,
    )
    assert "wir kümmern uns um" in applied["body"]
    listed = _ok(client.get(f"{M}/playbooks", headers=admin))
    assert next(p for p in listed if p["id"] == playbook["id"])["usage_count"] == 1

    recomputed = _ok(client.post(f"{M}/messages/{msg['id']}/suggest", headers=admin))
    assert recomputed["suggestion_status"] == "ready"


def test_read_only_forbidden_on_write_endpoints(client: TestClient, world: World) -> None:
    reader = bearer(login(client, world, "sgreader"))
    assert client.get(f"{M}/playbooks", headers=reader).status_code == 200
    assert (
        client.post(f"{M}/playbooks", json={"title": f"X {RUN}"}, headers=reader).status_code == 403
    )
    raw = _eml(f"m3{RUN}@example.com", "Test", f"<sg3-{RUN}@x>", "Text")
    doc = _upload(client, bearer(login(client, world, "sgadmin")), "m3.eml", raw)
    assert client.post(f"{M}/ingest", json={"document_id": doc}, headers=reader).status_code == 403
