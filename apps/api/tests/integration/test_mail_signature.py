"""E-Mail-Signatur (operator 27.09.2026): eigene Position pflegen (Freitext wird im
Mandantenkatalog gemerkt), Vorschau eigener und fremder Signatur, Admin setzt Position
anderer Mitglieder, Rechte (fremde Vorschau nur mit ``members:read``, Mandantengrenze),
Vorlage über die Mandanteneinstellungen."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, _settings, bearer, login

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
