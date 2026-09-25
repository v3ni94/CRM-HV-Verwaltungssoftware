"""M30 handover protocols: prefill from unit, sub records, photos, signatures, hints, completion
with PDF, new version referencing the same files, authorization and tenant separation.

Expected values by hand: number UP-<today>-001 for the first protocol of the day per tenant,
UP-<today>-002 for the second; a new version keeps the number and gets version 2; the copy
holds the same count of rooms, defects, meters and signatures and links the same photo
document (one document, two protocol links); a read-only member gets 403 on create; a member
of another tenant gets 404 on read (RLS)."""

import asyncio
import base64
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/handover/protocols"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _signature_png() -> bytes:
    """A real PNG above the 100 byte minimum, drawn with reportlab is not possible; use PIL
    free approach: repeat the 1x1 PNG chunks is invalid, so build a tiny 40x12 PNG by hand."""
    import struct
    import zlib

    width, height = 160, 48
    raw = b"".join(
        b"\x00" + bytes([0 if (x // 4 + y) % 3 else 255 for x in range(width)])
        for y in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ho30-{RUN}", name=f"HO {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ho30b-{RUN}", name=f"HO B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("m30admin", a, "tenant_admin"),
            ("m30reader", a, "read_only"),
            ("m30other", b, "tenant_admin"),
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
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _jpeg() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 100, 50)).save(buffer, "JPEG")
    return buffer.getvalue()


def _unit(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "830",
                "name": "Übergabehaus",
                "management_type": "rental",
                "street": "Musterweg",
                "house_number": "12",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={"building_id": building, "number": "03", "unit_type": "apartment", "floor": "2"},
            headers=h,
        ),
        201,
    )["id"]
    return prop["id"], unit


def test_handover_flow(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m30admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    _, unit_id = _unit(client, h)
    stamp = datetime.now(UTC).strftime("%Y%m%d")

    # Prefill from unit and property: the unit has no own address, the property address wins.
    pre = _ok(client.get(f"{H}/prefill", params={"unit_id": unit_id}, headers=h))
    assert pre["street"] == "Musterweg"
    assert pre["floor"] == "2"
    assert pre["unit_number"] == "03"

    p = _ok(client.post(H, json={"kind": "rental", "unit_id": unit_id}, headers=h), 201)
    assert p["number"] == f"UP-{stamp}-001"
    assert p["address"] == "Musterweg 12, 40789 Monheim am Rhein"
    assert p["status"] == "draft"
    assert p["version"] == 1
    assert not p["locked"]
    pid = p["id"]
    second = _ok(client.post(H, json={"kind": "general"}, headers=h), 201)
    assert second["number"] == f"UP-{stamp}-002"
    assert second["address"] == ""

    # Autosave style patch, unknown field rejected, deposit as decimal string.
    _ok(
        client.patch(
            f"{H}/{pid}", json={"ticket_number": "T-4711", "deposit_amount": "1500.00"}, headers=h
        )
    )
    assert client.patch(f"{H}/{pid}", json={"foo": 1}, headers=h).status_code == 422
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "in_progress"

    # Participants: from a CRM contact (snapshot of name and e-mail) and free text.
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Erika",
                "last_name": f"Mieter{RUN}",
                "emails": [{"email": f"erika.{RUN}@example.org", "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    mover = _ok(
        client.post(
            f"{H}/{pid}/participants",
            json={"contact_id": contact["id"], "role": "moving_in"},
            headers=h,
        ),
        201,
    )
    assert mover["last_name"] == f"Mieter{RUN}"
    assert mover["email"] == f"erika.{RUN}@example.org"
    assert mover["role_label"] == "Einziehender Mieter"
    _ok(
        client.post(
            f"{H}/{pid}/participants", json={"role": "management", "company": "HVM"}, headers=h
        ),
        201,
    )
    assert (
        client.post(f"{H}/{pid}/participants", json={"role": "boss"}, headers=h).status_code == 422
    )
    assert client.post(f"{H}/{pid}/unknown", json={}, headers=h).status_code == 422

    # Meters, rooms with a defect, keys, items, notes (one internal).
    meter = _ok(
        client.post(
            f"{H}/{pid}/meters",
            json={
                "meter_type": "electricity",
                "number": "E-1",
                "value": "12345.678",
                "unit": "kWh",
            },
            headers=h,
        ),
        201,
    )
    room = _ok(
        client.post(
            f"{H}/{pid}/rooms", json={"name": "Küche", "condition": "defective"}, headers=h
        ),
        201,
    )
    defect = _ok(
        client.post(
            f"{H}/{pid}/defects",
            json={
                "room_id": room["id"],
                "title": "Kratzer",
                "priority": "low",
                "defect_status": "new",
            },
            headers=h,
        ),
        201,
    )
    foreign_room = _ok(
        client.post(f"{H}/{second['id']}/rooms", json={"name": "Flur"}, headers=h), 201
    )
    assert (
        client.post(
            f"{H}/{pid}/defects", json={"room_id": foreign_room["id"], "title": "x"}, headers=h
        ).status_code
        == 422
    )
    _ok(
        client.post(
            f"{H}/{pid}/keys",
            json={"key_type": "Haustürschlüssel", "quantity": 2, "status": "handed_over"},
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{H}/{pid}/items", json={"name": "Müllkarte", "quantity": 1}, headers=h), 201)
    _ok(
        client.post(
            f"{H}/{pid}/notes",
            json={"category": "hint", "text": "Nur intern", "is_internal": True},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{H}/{pid}/meters/{meter['id']}", json={"value": "12346.000"}, headers=h))
    _ok(client.post(f"{H}/{pid}/rooms/order", json={"ids": [room["id"]]}, headers=h))

    # Photo for the defect, attachment without sub record.
    photo = _ok(
        client.post(
            f"{H}/{pid}/documents",
            files={"file": ("mangel.jpg", _jpeg(), "image/jpeg")},
            data={"section": "defects", "item_id": defect["id"]},
            headers=h,
        ),
        201,
    )
    assert photo["kind"] == "photo"
    assert photo["section"] == "defect"
    assert photo["item_id"] == defect["id"]
    pdf_buffer = io.BytesIO()
    canvas = Canvas(pdf_buffer, pagesize=A4)
    canvas.drawString(72, 720, "Anlage")
    canvas.save()
    attachment = _ok(
        client.post(
            f"{H}/{pid}/documents",
            files={"file": ("anlage.pdf", pdf_buffer.getvalue(), "application/pdf")},
            headers=h,
        ),
        201,
    )
    assert attachment["kind"] == "attachment"

    # Hints before completion, then signatures (one per participant at most).
    hints = _ok(client.get(f"{H}/{pid}/hints", headers=h))["hints"]
    assert "Es liegt keine Unterschrift vor." in hints
    data_uri = "data:image/png;base64," + base64.b64encode(_signature_png()).decode()
    sig = _ok(
        client.post(
            f"{H}/{pid}/signatures",
            json={
                "image": data_uri,
                "signer_name": "Erika",
                "signer_role": "moving_in",
                "participant_id": mover["id"],
            },
            headers=h,
        ),
        201,
    )
    assert len(sig["sha256"]) == 64
    dup = client.post(
        f"{H}/{pid}/signatures",
        json={"image": data_uri, "signer_name": "Erika", "participant_id": mover["id"]},
        headers=h,
    )
    assert dup.status_code == 409
    assert (
        client.post(
            f"{H}/{pid}/signatures", json={"image": "data:image/png;base64," + "A" * 120}, headers=h
        ).status_code
        == 422
    )
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "signature_pending"

    # Preview PDF while open carries the draft mark; internal note never appears.
    preview = client.get(f"{H}/{pid}/pdf", headers=h)
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(preview.content)).pages)
    assert "ENTWURF" in text
    assert "Nur intern" not in text
    assert "Kratzer" in text
    assert "1.500,00 EUR" in text

    # Completion needs force while hints exist (the empty second protocol); the filled one
    # completes without force and is locked afterwards.
    blocked = client.post(f"{H}/{second['id']}/complete", json={"force": False}, headers=h)
    assert blocked.status_code == 422
    assert "keine beteiligten Personen" in blocked.json()["detail"]
    assert _ok(client.get(f"{H}/{pid}/hints", headers=h))["hints"] == []
    done = _ok(client.post(f"{H}/{pid}/complete", json={"force": False}, headers=h))
    assert done["status"] == "completed"
    assert done["locked"]
    assert done["pdf_document_id"]
    assert client.patch(f"{H}/{pid}", json={"city": "Köln"}, headers=h).status_code == 409
    assert client.post(f"{H}/{pid}/rooms", json={"name": "Bad"}, headers=h).status_code == 409
    stored = client.get(f"{H}/{pid}/pdf", headers=h)
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(stored.content)).pages)
    assert "ENTWURF" not in text
    assert "Abgeschlossen und festgeschrieben" in text
    assert "Amtsgericht Düsseldorf, HRB 104762" in text
    documents = _ok(client.get(f"{H}/{pid}", headers=h))["documents"]
    assert {d["kind"] for d in documents} == {"photo", "attachment", "signature", "pdf"}

    # New version: same number, version 2, copies of all sub records, same photo document.
    v2 = _ok(
        client.post(f"{H}/{pid}/versions", json={"reason": "Zählerstand korrigiert"}, headers=h),
        201,
    )
    assert v2["number"] == p["number"]
    assert v2["version"] == 2
    assert v2["status"] == "in_progress"
    assert len(v2["rooms"]) == 1
    assert len(v2["defects"]) == 1
    assert len(v2["meters"]) == 1
    assert v2["defects"][0]["room_id"] == v2["rooms"][0]["id"]
    assert len(v2["signatures"]) == 1
    assert v2["signatures"][0]["sha256"] == sig["sha256"]
    v2_photo = [d for d in v2["documents"] if d["kind"] == "photo"]
    assert len(v2_photo) == 1
    assert v2_photo[0]["id"] == photo["id"]
    assert v2_photo[0]["item_id"] == v2["defects"][0]["id"]
    assert [v["version"] for v in v2["versions"]] == [1, 2]
    assert (
        client.post(f"{H}/{pid}/versions", json={"reason": "noch eine"}, headers=h).status_code
        == 201
    )
    # The original stays as it was.
    original = _ok(client.get(f"{H}/{pid}", headers=h))
    assert original["status"] == "completed"
    assert len(original["rooms"]) == 1

    # Dispatch preparation: only participants with a CRM contact get a dispatch; e-mail becomes
    # a draft in the outbox (M20-01), nothing is sent.
    prepared = _ok(client.post(f"{H}/{pid}/dispatches", json={}, headers=h), 201)
    assert len(prepared["created"]) == 1
    assert prepared["created"][0]["channel"] == "email"
    assert len(prepared["skipped"]) == 1
    assert _ok(client.get(f"{H}/{pid}", headers=h))["status"] == "sent"
    assert client.post(f"{H}/{v2['id']}/dispatches", json={}, headers=h).status_code == 409

    # Listing: default hides archived, search by ticket, archive and restore.
    _ok(client.post(f"{H}/{pid}/status", json={"action": "archive"}, headers=h))
    listed = _ok(client.get(H, params={"q": "T-4711"}, headers=h))
    assert all(x["id"] != pid for x in listed["items"])
    listed = _ok(client.get(H, params={"q": "T-4711", "include_archived": "true"}, headers=h))
    assert any(x["id"] == pid for x in listed["items"])
    restored = _ok(client.post(f"{H}/{pid}/status", json={"action": "unarchive"}, headers=h))
    assert restored["status"] == "sent"
    cancelled = _ok(client.post(f"{H}/{second['id']}/status", json={"action": "cancel"}, headers=h))
    assert cancelled["status"] == "cancelled"
    assert cancelled["locked"]
    assert not cancelled["finalized"]

    # Authorization and tenant separation.
    reader = bearer(login(client, world, "m30reader"))
    assert client.get(f"{H}/{pid}", headers=reader).status_code == 200
    assert client.post(H, json={"kind": "rental"}, headers=reader).status_code == 403
    assert client.patch(f"{H}/{v2['id']}", json={"city": "x"}, headers=reader).status_code == 403
    other = bearer(login(client, world, "m30other"))
    assert client.get(f"{H}/{pid}", headers=other).status_code == 404
    assert client.get(f"{H}/{pid}/pdf", headers=other).status_code == 404
    assert _ok(client.get(H, headers=other))["total"] == 0
    other_first = _ok(client.post(H, json={"kind": "sale"}, headers=other), 201)
    assert other_first["number"] == f"UP-{stamp}-001"  # sequence per tenant


def test_signature_png_is_valid() -> None:
    png = _signature_png()
    assert png.startswith(b"\x89PNG")
    assert len(png) > 100
    assert isinstance(UUID(int=0), UUID)
