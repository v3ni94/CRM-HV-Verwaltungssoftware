"""AF11 (GAB-06, 11.3): hoa statement PDFs are filed once in the DMS and served from there.

Expected by hand: the first output of the individual statement of unit 01 files exactly one
document linked to statement, property, community, unit and the owner contact; a second
output (CRM or owner portal) returns byte identical content and files nothing new; the
provision (transition issued) files one document per snapshot unit, idempotently. Another
tenant gets 404, G4 closed gives 403, the statement values stay unchanged.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_a61_inspection import _world
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_board_portal import _doc, _ledger_with_invoice
from tests.integration.test_m21_portal import _contact_of, _portal_user
from tests.integration.test_r05_positive_paths import (
    OpenG4,
    _community,
    _ledger_of,
    _ok,
    _run,
    _statement,
)

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    async def build() -> World:
        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.platform import services

        settings = _settings(database, redis_url)
        w = await _world(settings, "af11", "af11admin", "af11reader")
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            b, _ = await services.provision_tenant(factory, slug=f"af11b-{RUN}", name="AF11b")
            uid = await services.create_user(
                factory, email=w.email("af11other"), display_name="o", password=PASSWORD
            )
            w.users["af11other"] = uid
            await services.add_member(
                factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        finally:
            await engine.dispose()
        return w

    return asyncio.run(build())


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
        ):
            yield closed, open_


def _links(database: Database, redis_url: str, world: World, st: UUID) -> list[Any]:
    from mhvp.documents.models import Document, DocumentLink

    async def fn(session: Any) -> list[Any]:
        docs = (
            await session.scalars(
                select(Document)
                .join(DocumentLink, DocumentLink.document_id == Document.id)
                .where(DocumentLink.entity_type == "hoa_statement", DocumentLink.entity_id == st)
            )
        ).all()
        out = []
        for d in docs:
            links = (
                await session.scalars(select(DocumentLink).where(DocumentLink.document_id == d.id))
            ).all()
            out.append(
                (
                    d.filename,
                    d.source.value,
                    sorted((x.entity_type, str(x.entity_id)) for x in links),
                )
            )
        return out

    return _run(database, redis_url, world, fn)  # type: ignore[no-any-return]


def _snapshot(database: Database, redis_url: str, world: World, st: UUID) -> Any:
    from mhvp.hoa.models import HoaStatement

    async def fn(session: Any) -> Any:
        row = await session.get(HoaStatement, st)
        return row.snapshot, row.snapshot_hash, row.status.value

    return _run(database, redis_url, world, fn)


def test_unit_pdf_filed_once_and_served_identically(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, open_ = clients
    h = bearer(login(open_, world, "af11admin"))
    com = _community(open_, h, "911")
    _ledger_with_invoice(open_, h, com["hoa"], "911", _doc(open_, h, "a.pdf", b"%PDF-1.4 af11911"))
    owner = _portal_user(open_, h, world, "af11own", _contact_of(open_, h, com["party"]))
    st = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, com["hoa"]),
        com["unit"], "issued", 2025,
    )  # fmt: skip
    before = _snapshot(database, redis_url, world, st)
    url = f"{H}/statements/{st}/units/{com['unit']}/pdf"
    assert closed.get(url, headers=h).status_code == 403
    assert _links(database, redis_url, world, st) == []

    first = open_.get(url, headers=h)
    assert first.status_code == 200, first.text
    assert first.content.startswith(b"%PDF")
    filed = _links(database, redis_url, world, st)
    assert len(filed) == 1
    name, source, links = filed[0]
    assert name == "hausgeldabrechnung-2025-01-v1-aaaaaaaaaaaa.pdf"
    assert source == "generated"
    kinds = {k for k, _ in links}
    assert kinds == {"hoa_statement", "property", "legal_entity", "unit", "contact"}
    assert ("unit", com["unit"]) in links
    assert ("legal_entity", com["hoa"]) in links

    second = open_.get(url, headers=h)
    assert second.content == first.content
    portal = open_.get(f"{P}/owner/statements/{st}/units/{com['unit']}/pdf", headers=owner)
    assert portal.status_code == 200, portal.text
    assert portal.content == first.content
    assert len(_links(database, redis_url, world, st)) == 1
    assert _snapshot(database, redis_url, world, st) == before

    # Another tenant never reaches the filed document.
    other = bearer(login(open_, world, "af11other"))
    assert open_.get(url, headers=other).status_code == 404


def test_portal_files_on_first_output(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    _, open_ = clients
    h = bearer(login(open_, world, "af11admin"))
    com = _community(open_, h, "912")
    _ledger_with_invoice(open_, h, com["hoa"], "912", _doc(open_, h, "a.pdf", b"%PDF-1.4 af11912"))
    owner = _portal_user(open_, h, world, "af11own2", _contact_of(open_, h, com["party"]))
    st = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, com["hoa"]),
        com["unit"], "issued", 2025,
    )  # fmt: skip
    purl = f"{P}/owner/statements/{st}/units/{com['unit']}/pdf"
    a = open_.get(purl, headers=owner)
    assert a.status_code == 200, a.text
    assert len(_links(database, redis_url, world, st)) == 1
    crm = open_.get(f"{H}/statements/{st}/units/{com['unit']}/pdf", headers=h)
    assert crm.content == a.content
    assert len(_links(database, redis_url, world, st)) == 1


def test_new_snapshot_version_files_new_document(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    from mhvp.hoa.models import HoaStatement

    _, open_ = clients
    h = bearer(login(open_, world, "af11admin"))
    com = _community(open_, h, "913")
    _ledger_with_invoice(open_, h, com["hoa"], "913", _doc(open_, h, "a.pdf", b"%PDF-1.4 af11913"))
    st = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, com["hoa"]),
        com["unit"], "issued", 2025,
    )  # fmt: skip
    url = f"{H}/statements/{st}/units/{com['unit']}/pdf"
    assert open_.get(url, headers=h).status_code == 200

    async def rehash(session: Any) -> None:
        row = await session.get(HoaStatement, st)
        row.snapshot_hash = "b" * 64

    _run(database, redis_url, world, rehash)
    open_.get(url, headers=h)
    open_.get(url, headers=h)
    names = sorted(n for n, _, _ in _links(database, redis_url, world, st))
    assert names == [
        "hausgeldabrechnung-2025-01-v1-aaaaaaaaaaaa.pdf",
        "hausgeldabrechnung-2025-01-v1-bbbbbbbbbbbb.pdf",
    ]


def test_provision_files_every_unit_once(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, open_ = clients
    h = bearer(login(open_, world, "af11admin"))
    com = _community(open_, h, "915")
    _ledger_with_invoice(open_, h, com["hoa"], "915", _doc(open_, h, "a.pdf", b"%PDF-1.4 af11915"))
    st = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, com["hoa"]),
        com["unit"], "resolved", 2025,
    )  # fmt: skip
    url = f"{H}/statements/{st}/transition"
    assert closed.post(url, json={"target": "issued"}, headers=h).status_code == 403
    assert _links(database, redis_url, world, st) == []
    _ok(open_.post(url, json={"target": "issued"}, headers=h))
    assert [n for n, _, _ in _links(database, redis_url, world, st)] == [
        "hausgeldabrechnung-2025-01-v1-aaaaaaaaaaaa.pdf"
    ]
    _ok(open_.post(url, json={"target": "due"}, headers=h))
    assert len(_links(database, redis_url, world, st)) == 1


def test_before_approval_nothing_is_filed(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    _, open_ = clients
    h = bearer(login(open_, world, "af11admin"))
    com = _community(open_, h, "914")
    _ledger_with_invoice(open_, h, com["hoa"], "914", _doc(open_, h, "a.pdf", b"%PDF-1.4 af11914"))
    st = _statement(
        database, redis_url, world, _ledger_of(database, redis_url, world, com["hoa"]),
        com["unit"], "calculated", 2025,
    )  # fmt: skip
    url = f"{H}/statements/{st}/units/{com['unit']}/pdf"
    assert open_.get(url, headers=h).status_code == 409  # before approval: nothing filed
    assert _links(database, redis_url, world, st) == []
