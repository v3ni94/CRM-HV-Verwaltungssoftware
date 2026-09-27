"""M19-02 (docs/rules/M19-02-beiratsbeteiligung.md): submissions of tickets and work orders to
the Verwaltungsbeirat of a WEG for information or an opinion.

Board members are the property contacts of category ``board``; only they see the submission
in the portal (another owner of the same WEG and a board of another tenant get 404), they
answer until the deadline, the management records answers received elsewhere and closes the
submission. The vote is information only: the work order release stays with the management
and still needs the note (existing rule), no payment is created.
"""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.tickets import board
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"
T = "/api/v1/tickets"
B = "/api/v1/portal/board/submissions"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bs-{RUN}", name=f"Beirat S {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"bs2-{RUN}", name=f"Beirat T {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("bsadmin", a, "tenant_admin"),
            ("bsreader", a, "read_only"),
            ("bsadmin_b", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _contact_of(c: TestClient, h: dict[str, str], party: str) -> str:
    return str(_ok(c.get(f"/api/v1/parties/{party}", headers=h))["members"][0]["contact_id"])


def _owner(c: TestClient, h: dict[str, str], prop: str, unit_no: str, name: str) -> str:
    """Unit, owner party and ownership contract; returns the owner's contact id."""
    unit = _unit(c, h, prop, unit_no)
    party, _ = _party(c, h, name)
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    return _contact_of(c, h, party)


def _portal_user(
    c: TestClient, h: dict[str, str], world: World, name: str, contact_id: str
) -> dict[str, str]:
    inv = _ok(
        c.post(
            f"{PA}/accounts",
            json={"contact_id": contact_id, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{P}/invitations/accept", json={"token": inv["invitation_token"], "password": PASSWORD}
        )
    )
    return bearer(login(c, world, name))


def _property(c: TestClient, h: dict[str, str], number: str, hoa: bool = True) -> str:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Objekt {number}",
                "management_type": "hoa" if hoa else "rental",
            },
            headers=h,
        ),
        201,
    )
    return str(prop["id"])


def _board_contact(c: TestClient, h: dict[str, str], prop: str, contact_id: str) -> None:
    _ok(
        c.post(
            f"/api/v1/properties/{prop}/contacts",
            json={
                "contact_id": contact_id,
                "category_code": "board",
                "valid_from": "2024-01-01",
                "visible_in_portal_for": ["owner"],
            },
            headers=h,
        ),
        201,
    )


def _ticket(c: TestClient, h: dict[str, str], prop: str, **extra: Any) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            T,
            json={
                "title": "Fassade sanieren",
                "priority": "normal",
                "property_id": prop,
                "category": "instandhaltung",
                **extra,
            },
            headers=h,
        ),
        201,
    )


def test_board_submission_roles_deadline_protocol_and_tenant_separation(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = bearer(login(client, world, "bsadmin"))
    reader = bearer(login(client, world, "bsreader"))
    hb = bearer(login(client, world, "bsadmin_b", tenant_id=world.tenant_b))
    today = board._today()

    weg = _property(client, h, "801")
    board_member = _owner(client, h, weg, "01", "Beirat")
    plain_owner = _owner(client, h, weg, "02", "Eigentuemer")
    _board_contact(client, h, weg, board_member)
    board_portal = _portal_user(client, h, world, "bsboard", board_member)
    owner_portal = _portal_user(client, h, world, "bsowner", plain_owner)

    # Policy: recommendation only (category instandhaltung by default, amount configurable).
    policy = _ok(client.get(f"{T}/board/policy", headers=h))
    assert policy["categories"] == ["instandhaltung"]
    assert policy["threshold_amount"] is None
    assert (
        client.put(
            f"{T}/board/policy", json={"threshold_amount": "5000.00"}, headers=reader
        ).status_code
        == 403
    )
    _ok(client.put(f"{T}/board/policy", json={"threshold_amount": "5000.00"}, headers=h))

    ticket = _ticket(client, h, weg)
    provider, _ = _party(client, h, "Dachdecker", kind="company")
    provider_contact = _contact_of(client, h, provider)
    order = _ok(
        client.post(
            f"{T.rsplit('/', 1)[0]}/work-orders",
            json={
                "ticket_id": ticket["id"],
                "property_id": weg,
                "provider_contact_id": provider_contact,
                "description": "Fassade sanieren laut Angebot",
            },
            headers=h,
        ),
        201,
    )
    steps = f"{T.rsplit('/', 1)[0]}/work-orders/{order['id']}/steps"
    _ok(client.post(steps, json={"status": "requested"}, headers=h))
    _ok(client.post(steps, json={"status": "quoted", "quote_amount": "7500.00"}, headers=h))

    overview = _ok(client.get(f"{T}/{ticket['id']}/board-submissions", headers=h))
    assert overview["is_hoa"] is True
    assert [m["contact_id"] for m in overview["members"]] == [board_member]
    assert overview["recommendation"]["recommended"] is True
    assert overview["recommendation"]["by_amount"] is True
    assert overview["submissions"] == []

    # Read only cannot submit; a deadline in the past is rejected; a rental property has no board.
    due = (today + timedelta(days=14)).isoformat()
    body = {"kind": "consent", "due_on": due, "work_order_id": order["id"], "note": "Bitte Votum"}
    assert (
        client.post(f"{T}/{ticket['id']}/board-submissions", json=body, headers=reader).status_code
        == 403
    )
    assert (
        client.post(
            f"{T}/{ticket['id']}/board-submissions",
            json={**body, "due_on": (today - timedelta(days=1)).isoformat()},
            headers=h,
        ).status_code
        == 422
    )
    rental = _property(client, h, "802", hoa=False)
    rental_ticket = _ticket(client, h, rental)
    assert (
        client.post(
            f"{T}/{rental_ticket['id']}/board-submissions",
            json={"kind": "info", "due_on": due},
            headers=h,
        ).status_code
        == 422
    )
    weg_without_board = _property(client, h, "803")
    assert (
        client.post(
            f"{T}/{_ticket(client, h, weg_without_board)['id']}/board-submissions",
            json={"kind": "info", "due_on": due},
            headers=h,
        ).status_code
        == 409
    )

    submission = _ok(
        client.post(f"{T}/{ticket['id']}/board-submissions", json=body, headers=h), 201
    )
    assert submission["status"] == "open"
    assert submission["kind"] == "consent"
    assert submission["amount"] == "7500.00"
    assert [m["contact_id"] for m in submission["members"]] == [board_member]

    # Portal: only the board member of this WEG sees the submission; the plain owner and the
    # tenant B administrator see nothing (404 without a hint).
    mine = _ok(client.get(B, headers=board_portal))
    assert [s["id"] for s in mine] == [submission["id"]]
    assert mine[0]["can_vote"] is True
    assert mine[0]["my_votes"] == []
    assert _ok(client.get(B, headers=owner_portal)) == []
    assert client.get(f"{B}/{submission['id']}", headers=owner_portal).status_code == 404
    assert client.get(f"{T}/{ticket['id']}/board-submissions", headers=hb).status_code == 404
    assert (
        client.post(
            f"{T}/board/submissions/{submission['id']}/close", json={}, headers=hb
        ).status_code
        == 404
    )

    # Votes: comment needs a text; approve with comment from the portal; a second answer is
    # kept as protocol, not overwritten.
    assert (
        client.post(
            f"{B}/{submission['id']}/votes", json={"vote": "comment"}, headers=board_portal
        ).status_code
        == 422
    )
    voted = _ok(
        client.post(
            f"{B}/{submission['id']}/votes",
            json={"vote": "approve", "comment": "Einverstanden"},
            headers=board_portal,
        ),
        201,
    )
    assert voted["tally"] == {"approve": 1, "reject": 0, "comment": 0}
    assert voted["my_votes"][0]["vote"] == "approve"
    assert (
        client.post(
            f"{B}/{submission['id']}/votes", json={"vote": "approve"}, headers=owner_portal
        ).status_code
        == 404
    )

    # CRM records an answer received by letter; only a submitted member counts.
    assert (
        client.post(
            f"{T}/board/submissions/{submission['id']}/votes",
            json={"contact_id": plain_owner, "vote": "reject"},
            headers=h,
        ).status_code
        == 422
    )
    recorded = _ok(
        client.post(
            f"{T}/board/submissions/{submission['id']}/votes",
            json={"contact_id": board_member, "vote": "comment", "comment": "Brief vom 20.09."},
            headers=h,
        ),
        201,
    )
    assert [v["source"] for v in recorded["votes"]] == ["portal", "crm"]
    assert recorded["tally"]["comment"] == 1

    # Deadline: after due_on the portal refuses a vote (409), the management can still record.
    monkeypatch.setattr(board, "_today", lambda: today + timedelta(days=15))
    assert (
        client.post(
            f"{B}/{submission['id']}/votes", json={"vote": "reject"}, headers=board_portal
        ).status_code
        == 409
    )
    assert _ok(client.get(B, headers=board_portal))[0]["overdue"] is True
    monkeypatch.undo()

    # Release of the work order stays with the management and still needs the note; the
    # board vote itself releases nothing.
    assert client.post(steps, json={"status": "approved"}, headers=h).status_code == 422
    approved = _ok(
        client.post(
            steps, json={"status": "approved", "note": "Beirat zugestimmt, Vorlage 1"}, headers=h
        )
    )
    assert approved["status"] == "approved"

    closed = _ok(
        client.post(
            f"{T}/board/submissions/{submission['id']}/close",
            json={"closing_note": "Votum liegt vor"},
            headers=h,
        )
    )
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None
    assert (
        client.post(
            f"{B}/{submission['id']}/votes", json={"vote": "approve"}, headers=board_portal
        ).status_code
        == 409
    )

    # Protocol on the ticket: submission, both votes and the closing.
    events = _ok(client.get(f"{T}/{ticket['id']}", headers=h))["events"]
    kinds = [e["kind"] for e in events]
    assert kinds.count("board_submission") == 1
    assert kinds.count("board_vote") == 2
    assert kinds.count("board_submission_closed") == 1
