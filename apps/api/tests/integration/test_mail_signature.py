"""E-Mail-Signatur (operator 27.09.2026): eigene Position pflegen (Freitext wird im
Mandantenkatalog gemerkt), Vorschau eigener und fremder Signatur, Admin setzt Position
anderer Mitglieder, Rechte (fremde Vorschau nur mit ``members:read``, Mandantengrenze),
Vorlage über die Mandanteneinstellungen."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    World,
    _settings,
    bearer,
    enable_totp,
    login,
)

pytestmark = pytest.mark.integration
S = "/api/v1/mail/signature"


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(res: Any, status: int = 200) -> Any:
    assert res.status_code == status, res.text
    return res.json() if res.content else None


def test_profile_preview_and_admin_position(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "admin", world.tenant_a))
    reader = bearer(login(client, world, "reader", world.tenant_a))

    profile = _ok(client.get(f"{S}/profile", headers=reader))
    assert profile["position"] is None
    assert profile["catalogue"][:2] == ["Geschäftsführer", "Prokurist"]

    # Freitext-Position des Lesers wird gemerkt und erscheint im Katalog.
    updated = _ok(
        client.put(
            f"{S}/profile",
            json={"position": "  Hausmeister  Service ", "phone": "02173 1"},
            headers=reader,
        )
    )
    assert updated["position"] == "Hausmeister Service"
    assert updated["phone"] == "02173 1"
    assert "Hausmeister Service" in updated["catalogue"]
    assert "Hausmeister Service" in _ok(
        client.get("/api/v1/tenant/position-catalogue", headers=admin)
    )

    preview = _ok(client.get(f"{S}/preview", headers=reader))
    assert preview["text"].startswith("-- \nreader\nHausmeister Service\n")
    assert "Telefon 02173 1" in preview["text"]
    assert preview["html"].startswith("<!-- mhvp-signature -->")
    reader_membership = preview["membership_id"]

    # Fremde Vorschau braucht members:read (die Leserolle hat es, siehe READ_ALL).
    other = _ok(client.get(f"{S}/preview?membership_id={reader_membership}", headers=admin))
    assert other["membership_id"] == reader_membership

    # Admin setzt Position eines anderen Mitglieds; Liste zeigt sie.
    _ok(
        client.put(
            f"/api/v1/tenant/members/{reader_membership}/position",
            json={"position": "Buchhaltung", "phone": None},
            headers=admin,
        ),
        204,
    )
    members = _ok(client.get("/api/v1/tenant/members", headers=admin))
    row = next(m for m in members if m["membership_id"] == reader_membership)
    assert row["position"] == "Buchhaltung"
    assert row["phone"] is None
    assert (
        client.put(
            f"/api/v1/tenant/members/{reader_membership}/position",
            json={"position": "x"},
            headers=reader,
        ).status_code
        == 403
    )
    assert client.put(f"{S}/profile", json={"phone": "abc"}, headers=reader).status_code == 422


def test_template_from_settings_and_tenant_boundary(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "admin", world.tenant_a))
    both_b = bearer(login(client, world, "both", world.tenant_b))
    settings = _ok(client.get("/api/v1/tenant/settings", headers=admin))
    assert settings["signature_template"] == {"text": None, "html": None, "logo_url": None}
    _ok(
        client.patch(
            "/api/v1/tenant/settings",
            json={
                "signature_template": {"text": "{name}\nMandant A", "html": None, "logo_url": None},
                "position_catalogue_extra": ["Empfang"],
            },
            headers=admin,
        )
    )
    preview = _ok(client.get(f"{S}/preview", headers=admin))
    assert preview["text"] == "-- \nadmin\nMandant A"
    assert "Empfang" in _ok(client.get(f"{S}/profile", headers=admin))["catalogue"]
    # Mandant B sieht weder Vorlage noch Katalogerweiterung von A; fremde Mitgliedschaft 404.
    assert "Mandant A" not in _ok(client.get(f"{S}/preview", headers=both_b))["text"]
    assert "Empfang" not in _ok(client.get(f"{S}/profile", headers=both_b))["catalogue"]
    # Rolle standard in B ohne members:read: 403; mit Recht wäre es 404 (fremder Mandant).
    foreign = client.get(f"{S}/preview?membership_id={preview['membership_id']}", headers=both_b)
    assert foreign.status_code in (403, 404)
    assert (
        client.patch(
            "/api/v1/tenant/settings",
            json={"signature_template": {"logo_url": "http://insecure/logo.png"}},
            headers=admin,
        ).status_code
        == 422
    )
    # Review 1.36.0: unbekannte Platzhalter werden beim Speichern mit ihren Namen abgelehnt,
    # die gespeicherte Vorlage bleibt unverändert.
    refused = client.patch(
        "/api/v1/tenant/settings",
        json={"signature_template": {"text": "{name}\n{firma}\n{company.name}", "html": "{name}"}},
        headers=admin,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["unknown_placeholders"] == ["company.name", "firma"]
    assert "{firma}" in refused.json()["detail"]
    assert _ok(client.get(f"{S}/preview", headers=admin))["text"] == "-- \nadmin\nMandant A"


def test_signature_endpoints_for_member_with_second_factor(
    database: Database, redis_url: str, client: TestClient, world: World
) -> None:
    """Order independent regression for the CryptoError above: whether ``admin`` of the
    shared session world has TOTP depends on whether test_m2_platform ran first. A dedicated
    member with the second factor switched on always takes that path; ``totp_secret`` is sealed
    in the platform scope and is never decrypted in the tenant session."""
    name = "sig2fa"
    if name not in world.users:

        async def _member() -> uuid.UUID:
            engine = create_app_engine(_settings(database, redis_url))
            try:
                factory = create_session_factory(engine)
                uid = await services.create_user(
                    factory, email=world.email(name), display_name=name, password=PASSWORD
                )
                await services.add_member(
                    factory,
                    tenant_id=world.tenant_a,
                    user_id=uid,
                    role_codes=["standard"],
                    actor_user_id=None,
                )
                return uid
            finally:
                await engine.dispose()

        world.users[name] = asyncio.run(_member())
    if name not in world.secrets:
        enable_totp(client, world, name)
    member = bearer(login(client, world, name, world.tenant_a))
    assert _ok(client.get("/api/v1/auth/me", headers=member))["totp_enabled"] is True
    assert _ok(client.get(f"{S}/preview", headers=member))["text"].startswith(f"-- \n{name}\n")
    assert _ok(client.get(f"{S}/profile", headers=member))["position"] is None
    updated = _ok(client.put(f"{S}/profile", json={"position": "Empfang"}, headers=member))
    assert updated["position"] == "Empfang"
