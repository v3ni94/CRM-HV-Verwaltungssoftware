"""M35: channel selection per escalation level, SMS template rendering, delivery errors
without gateway or mailbox, e-mail text. HTTP is mocked with ``httpx.MockTransport``."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from mhvp.core.config import Settings
from mhvp.sla import channels, escalation
from mhvp.sla.models import AlertChannel, OnCallSchedule, SlaClock, SlaRule, SmsGateway
from mhvp.tickets.models import Priority, Ticket

TENANT = uuid.UUID("01900000-0000-7000-8000-000000000001")


def _ticket() -> Ticket:
    return Ticket(
        id=uuid.UUID("01900000-0000-7000-8000-0000000000aa"),
        tenant_id=TENANT,
        number=4711,
        title="Wasserrohrbruch Keller",
        priority=Priority.IMMEDIATE,
    )


def _gateway(**kw: Any) -> SmsGateway:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "enabled": True,
        "url": "https://gateway.example/api/sms",
        "method": "POST",
        "auth_header_name": "X-Api-Key",
        "auth_header_value": "geheim-123",
        "body_template": '{"to": "{to}", "text": "{text}", "from": "{sender}"}',
        "sender": "MHVP",
    }
    values.update(kw)
    return SmsGateway(**values)


def _settings() -> Settings:
    # Only ``web_crm_url`` is read here; a stand-in avoids the required secret settings.
    return cast(Settings, SimpleNamespace(web_crm_url="https://crm.example/"))


# --- Kanalauswahl ------------------------------------------------------------


def test_default_channels_per_level() -> None:
    assert channels.channels_for_level(None, 1) == [AlertChannel.INTERNAL]
    assert channels.channels_for_level(None, 2) == [AlertChannel.INTERNAL, AlertChannel.EMAIL]
    assert channels.channels_for_level(None, 3) == [
        AlertChannel.INTERNAL,
        AlertChannel.EMAIL,
        AlertChannel.SMS,
    ]
    assert channels.channels_for_level(None, 7) == channels.channels_for_level(None, 3)


def test_rule_overrides_level_and_falls_back_for_others() -> None:
    rule = SlaRule(channels_by_level={"1": ["sms", "sms", "unknown"], "2": []})
    assert channels.channels_for_level(rule, 1) == [AlertChannel.SMS]
    assert channels.channels_for_level(rule, 2) == []
    assert channels.channels_for_level(rule, 3)[-1] == AlertChannel.SMS


def test_validate_channels_by_level() -> None:
    assert channels.validate_channels_by_level({"1": ["internal", "sms"]}) is None
    assert channels.validate_channels_by_level({"x": ["internal"]}) is not None
    assert channels.validate_channels_by_level({"1": ["fax"]}) == "Unbekannte Kanäle: fax."


# --- SMS -------------------------------------------------------------------


def test_render_sms_body_escapes_json() -> None:
    body = channels.render_sms_body(
        '{"to": "{to}", "text": "{text}"}', "+49 170 1234567", 'Rohr "Keller"\nsofort', None
    )
    assert json.loads(body) == {"to": "+49 170 1234567", "text": 'Rohr "Keller"\nsofort'}


def test_render_sms_body_rejects_invalid_template() -> None:
    with pytest.raises(json.JSONDecodeError):
        channels.render_sms_body('{"to": {to}}', "+49", "x", None)


def test_send_sms_posts_rendered_template() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Api-Key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": "100"})

    error = asyncio.run(
        channels.send_sms(
            _gateway(), "+491701234567", "Hallo", http_transport=httpx.MockTransport(handler)
        )
    )
    assert error is None
    assert seen["method"] == "POST"
    assert seen["key"] == "geheim-123"
    assert seen["body"] == {"to": "+491701234567", "text": "Hallo", "from": "MHVP"}


def test_send_sms_http_error_hides_secret() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text="bad key geheim-123"))
    error = asyncio.run(channels.send_sms(_gateway(), "+49", "x", http_transport=transport))
    assert error == "SMS-Gateway meldet HTTP 401."


def test_send_sms_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    error = asyncio.run(
        channels.send_sms(_gateway(), "+49", "x", http_transport=httpx.MockTransport(handler))
    )
    assert error is not None
    assert "Zeitüberschreitung" in error


def test_send_sms_without_gateway_or_disabled() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected")

    mock = httpx.MockTransport(handler)
    assert asyncio.run(channels.send_sms(None, "+49", "x", http_transport=mock)) is not None
    disabled = _gateway(enabled=False)
    assert "deaktiviert" in (
        asyncio.run(channels.send_sms(disabled, "+49", "x", http_transport=mock)) or ""
    )


# --- E-Mail ------------------------------------------------------------------


def test_email_subject_and_body() -> None:
    ticket = _ticket()
    due = datetime(2026, 9, 25, 10, 0, tzinfo=UTC)
    link = channels.ticket_link(_settings(), ticket)
    assert link == f"https://crm.example/tickets/{ticket.id}"
    assert (
        channels.email_subject(ticket, 2)
        == "SLA-Eskalation Stufe 2: Ticket #4711 Wasserrohrbruch Keller"
    )
    body = channels.email_body(ticket, 2, "001 Musterstraße 1", due, link)
    assert "Objekt: 001 Musterstraße 1" in body
    assert "Priorität: Notfall" in body
    assert "Fälligkeit: 25.09.2026 12:00 Uhr" in body
    assert link in body


def test_send_email_without_mailbox(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_box(session: Any, tenant_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(channels, "default_mailbox", no_box)
    error = asyncio.run(
        channels.send_email(None, _settings(), TENANT, "a@example.org", "S", "B")  # type: ignore[arg-type]
    )
    assert error is not None
    assert "Postfach" in error


# --- Stufe auslösen ------------------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, model: Any, key: Any) -> None:
        return None


def test_level_three_without_gateway_or_mailbox_logs_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = uuid.UUID("01900000-0000-7000-8000-0000000000b1")
    notified: list[uuid.UUID] = []

    async def fake_notify(session: Any, **kw: Any) -> None:
        notified.append(kw["user_id"])

    async def fake_contacts(session: Any, tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> Any:
        return {user: ("bereitschaft@example.org", "+491701234567")}

    async def no_gateway(session: Any, tenant_id: uuid.UUID) -> None:
        return None

    async def no_mail(*args: Any) -> str:
        return "Kein Postfach für den Versand eingerichtet (M20-01)."

    monkeypatch.setattr(escalation, "notify", fake_notify)
    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)
    monkeypatch.setattr(escalation, "get_gateway", no_gateway)
    monkeypatch.setattr(escalation, "send_email", no_mail)
    on_call = OnCallSchedule(tenant_id=TENANT, user_id=user)
    alerts = asyncio.run(
        escalation.escalate_level(
            _FakeSession(),  # type: ignore[arg-type]
            _settings(),
            _ticket(),
            SlaClock(tenant_id=TENANT),
            None,
            3,
            [user],
            None,
            on_call,
        )
    )
    by_channel = {a.channel: a for a in alerts}
    assert set(by_channel) == {AlertChannel.INTERNAL, AlertChannel.EMAIL, AlertChannel.SMS}
    assert notified == [user]
    assert by_channel[AlertChannel.INTERNAL].delivered_at is not None
    assert by_channel[AlertChannel.EMAIL].delivery_error is not None
    assert by_channel[AlertChannel.EMAIL].delivered_at is None
    assert "nicht eingerichtet" in (by_channel[AlertChannel.SMS].delivery_error or "")
    assert by_channel[AlertChannel.SMS].sent_to == str(user)


def test_level_one_is_internal_only(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_notify(session: Any, **kw: Any) -> None:
        return None

    async def fake_contacts(*args: Any) -> dict[Any, Any]:
        return {}

    monkeypatch.setattr(escalation, "notify", fake_notify)
    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)
    user = uuid.uuid4()
    alerts = asyncio.run(
        escalation.escalate_level(
            _FakeSession(),  # type: ignore[arg-type]
            _settings(),
            _ticket(),
            SlaClock(tenant_id=TENANT),
            None,
            1,
            [user],
            "hausmeister",
            None,
        )
    )
    assert [a.channel for a in alerts] == [AlertChannel.INTERNAL, AlertChannel.INTERNAL]
    assert [a.sent_to for a in alerts] == [str(user), "hausmeister"]
