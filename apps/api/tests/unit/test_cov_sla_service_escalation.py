"""Coverage: SLA clock transitions (pause, resume, first response, resolve, reopen, colour) and
escalation channels (e-mail without address, SMS with on-call number, WhatsApp without number,
failed SMS fallback, internal alert for a role) with fake sessions; no database."""

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest

from mhvp.sla import escalation, service
from mhvp.sla.models import (
    AlertChannel,
    ClockState,
    ClockType,
    OnCallSchedule,
    SlaClock,
    SlaClockLog,
    SlaColor,
    SlaRule,
    WhatsAppConfig,
    WorkCalendar,
)
from mhvp.tickets.models import Priority, Ticket
from tests.conftest import make_settings

TENANT = uuid.UUID("01900000-0000-7000-8000-0000000000d0")


def _calendar() -> WorkCalendar:
    return WorkCalendar(
        tenant_id=TENANT,
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        opens_at=time(0, 0),
        closes_at=time(23, 59),
        timezone="Europe/Berlin",
        holidays=[],
    )


class _Session:
    def __init__(self, calendar: WorkCalendar | None = None) -> None:
        self.added: list[Any] = []
        self._calendar = calendar

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def scalar(self, query: Any) -> Any:
        return self._calendar

    async def get(self, model: Any, key: Any) -> None:
        return None

    def events(self) -> list[str]:
        return [row.event for row in self.added if isinstance(row, SlaClockLog)]


def _state(clock: SlaClock) -> str:
    """Current state as text (keeps mypy from narrowing the enum between transitions)."""
    return str(clock.state.value)


def _clock(**kw: Any) -> SlaClock:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": TENANT,
        "ticket_id": uuid.uuid4(),
        "started_at": now - timedelta(minutes=10),
        "due_response_at": now + timedelta(minutes=50),
        "due_resolution_at": now + timedelta(hours=3),
        "state": ClockState.RUNNING,
        "color": SlaColor.GREEN,
        "paused_minutes_total": 0,
        "escalated_steps": [],
    }
    values.update(kw)
    return SlaClock(**values)


def _ticket(**kw: Any) -> Ticket:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": TENANT,
        "number": 4711,
        "title": "Cov Heizung",
        "priority": Priority.URGENT,
    }
    values.update(kw)
    return Ticket(**values)


# --- clock transitions -------------------------------------------------------------------


def test_pause_only_running_clock() -> None:
    session = _Session()
    clock = _clock()
    asyncio.run(service.pause_clock(session, clock))  # type: ignore[arg-type]
    assert clock.state == ClockState.PAUSED
    assert clock.paused_at is not None
    assert session.events() == ["paused"]
    # a paused clock stays paused; nothing is logged twice
    asyncio.run(service.pause_clock(session, clock))  # type: ignore[arg-type]
    assert session.events() == ["paused"]
    done = _clock(state=ClockState.DONE)
    asyncio.run(service.pause_clock(session, done))  # type: ignore[arg-type]
    assert done.state == ClockState.DONE


def test_resume_shifts_resolution_due_by_paused_time() -> None:
    session = _Session(_calendar())
    due = datetime.now(UTC) + timedelta(hours=3)
    clock = _clock(
        state=ClockState.PAUSED,
        paused_at=datetime.now(UTC) - timedelta(minutes=30),
        due_resolution_at=due,
    )
    asyncio.run(service.resume_clock(session, TENANT, clock))  # type: ignore[arg-type]
    assert clock.state == ClockState.RUNNING
    assert clock.paused_at is None
    assert clock.paused_minutes_total in (29, 30)
    assert clock.due_resolution_at is not None
    assert clock.due_resolution_at > due
    assert session.events() == ["resumed"]
    # not paused: unchanged
    running = _clock()
    asyncio.run(service.resume_clock(session, TENANT, running))  # type: ignore[arg-type]
    assert running.state == ClockState.RUNNING
    assert session.events() == ["resumed"]


def test_resume_without_pause_duration_keeps_due_and_without_due() -> None:
    session = _Session(_calendar())
    clock = _clock(state=ClockState.PAUSED, paused_at=datetime.now(UTC), due_resolution_at=None)
    asyncio.run(service.resume_clock(session, TENANT, clock))  # type: ignore[arg-type]
    assert clock.state == ClockState.RUNNING
    assert clock.due_resolution_at is None
    assert clock.paused_minutes_total == 0


def test_first_response_resolve_reopen_are_idempotent() -> None:
    session = _Session()
    clock = _clock()
    asyncio.run(service.mark_first_response(session, clock))  # type: ignore[arg-type]
    first = clock.first_response_at
    assert first is not None
    asyncio.run(service.mark_first_response(session, clock))  # type: ignore[arg-type]
    assert clock.first_response_at == first
    asyncio.run(service.reopen_clock(session, clock))  # type: ignore[arg-type]
    assert _state(clock) == "running"  # not done: no change
    asyncio.run(service.mark_resolved(session, clock))  # type: ignore[arg-type]
    assert _state(clock) == "done"
    resolved = clock.resolved_at
    asyncio.run(service.mark_resolved(session, clock))  # type: ignore[arg-type]
    assert clock.resolved_at == resolved
    asyncio.run(service.reopen_clock(session, clock))  # type: ignore[arg-type]
    assert _state(clock) == "running"
    assert clock.resolved_at is None
    assert session.events() == ["first_response", "resolved", "reopened"]


def test_recompute_color_thresholds() -> None:
    session = _Session(_calendar())
    now = datetime.now(UTC)
    green = _clock(started_at=now - timedelta(minutes=10), due_response_at=now + timedelta(hours=2))
    assert asyncio.run(service.recompute_color(session, TENANT, green)) == SlaColor.GREEN  # type: ignore[arg-type]
    yellow = _clock(
        started_at=now - timedelta(minutes=70),
        due_response_at=now + timedelta(minutes=50),
        due_resolution_at=None,
    )
    assert asyncio.run(service.recompute_color(session, TENANT, yellow)) == SlaColor.YELLOW  # type: ignore[arg-type]
    assert yellow.state == ClockState.RUNNING
    red = _clock(started_at=now - timedelta(hours=2), due_response_at=now - timedelta(minutes=1))
    assert asyncio.run(service.recompute_color(session, TENANT, red)) == SlaColor.RED  # type: ignore[arg-type]
    assert red.state == ClockState.BREACHED
    # answered response clock is ignored; only the resolution clock counts
    answered = _clock(
        started_at=now - timedelta(hours=2),
        due_response_at=now - timedelta(minutes=1),
        first_response_at=now - timedelta(hours=1),
        due_resolution_at=now + timedelta(days=2),
    )
    assert asyncio.run(service.recompute_color(session, TENANT, answered)) == SlaColor.GREEN  # type: ignore[arg-type]
    done = _clock(state=ClockState.DONE, color=SlaColor.RED)
    assert asyncio.run(service.recompute_color(session, TENANT, done)) == SlaColor.GREEN  # type: ignore[arg-type]
    paused_red = _clock(
        state=ClockState.PAUSED,
        started_at=now - timedelta(hours=2),
        due_response_at=now - timedelta(minutes=1),
    )
    assert asyncio.run(service.recompute_color(session, TENANT, paused_red)) == SlaColor.RED  # type: ignore[arg-type]
    assert paused_red.state == ClockState.PAUSED  # only running clocks become breached


def test_due_at_calendar_versus_business() -> None:
    calendar = WorkCalendar(
        tenant_id=TENANT,
        weekdays=[0, 1, 2, 3, 4],
        opens_at=time(8, 0),
        closes_at=time(16, 30),
        timezone="Europe/Berlin",
        holidays=[],
    )
    start = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)  # Friday 16:00 Berlin
    assert service._due_at(calendar, start, 120, ClockType.CALENDAR) == start + timedelta(hours=2)
    business = service._due_at(calendar, start, 120, ClockType.BUSINESS)
    assert business > start + timedelta(days=2)  # rolls over the weekend


def test_default_rules_cover_all_priorities() -> None:
    assert set(service.DEFAULT_RULES) == set(Priority)
    assert all(r < s for r, s in service.DEFAULT_RULES.values())


# --- escalation channels ------------------------------------------------------------------


def _patch_common(monkeypatch: pytest.MonkeyPatch, contacts: dict[Any, Any]) -> None:
    async def fake_contacts(*args: Any) -> dict[Any, Any]:
        return contacts

    monkeypatch.setattr(escalation, "_user_contacts", fake_contacts)


def test_email_channel_without_address_and_role_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    user, silent = uuid.uuid4(), uuid.uuid4()
    sent: list[tuple[str, str]] = []

    async def fake_email(
        session: Any, settings: Any, tenant_id: Any, to: str, subject: str, body: str
    ) -> None:
        sent.append((to, subject))
        return None

    _patch_common(monkeypatch, {user: ("u@example.org", None)})
    monkeypatch.setattr(escalation, "send_email", fake_email)
    session = _Session()
    rule = SlaRule(channels_by_level={"1": ["internal", "email"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            session,  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            _clock(),
            rule,
            1,
            [user, silent, user],
            "tenant_admin",
            None,
        )
    )
    internal = [a for a in alerts if a.channel == AlertChannel.INTERNAL]
    assert {a.sent_to for a in internal} == {str(user), str(silent), "tenant_admin"}
    role_alert = next(a for a in internal if a.sent_to == "tenant_admin")
    assert role_alert.delivered_at is None  # a role is no user: no notification row
    user_alert = next(a for a in internal if a.sent_to == str(user))
    assert user_alert.delivered_at is not None
    emails = {a.sent_to: a for a in alerts if a.channel == AlertChannel.EMAIL}
    assert emails["u@example.org"].delivered_at is not None
    assert emails[str(silent)].delivery_error == "Keine E-Mail-Adresse des Benutzers gefunden."
    assert [to for to, _ in sent] == ["u@example.org"]


def test_sms_channel_uses_on_call_number_and_reports_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, duty = uuid.uuid4(), uuid.uuid4()
    numbers: list[str] = []

    async def fake_gateway(session: Any, tenant_id: Any) -> None:
        return None

    async def fake_sms(gateway: Any, to: str, text: str) -> str | None:
        numbers.append(to)
        return "Gateway lehnt ab." if to.endswith("9") else None

    _patch_common(
        monkeypatch, {user: ("u@example.org", "+49170000009"), duty: ("d@example.org", None)}
    )
    monkeypatch.setattr(escalation, "get_gateway", fake_gateway)
    monkeypatch.setattr(escalation, "send_sms", fake_sms)
    on_call = OnCallSchedule(tenant_id=TENANT, user_id=duty, phone="+49170000001")
    rule = SlaRule(channels_by_level={"2": ["sms"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _Session(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            _clock(),
            rule,
            2,
            [user],
            None,
            on_call,
        )
    )
    by_user = {a.sent_to: a for a in alerts}
    assert set(numbers) == {"+49170000009", "+49170000001"}
    assert by_user[str(user)].delivery_error == "Gateway lehnt ab."
    assert by_user[str(user)].delivered_at is None
    assert by_user[str(duty)].delivery_error is None
    assert by_user[str(duty)].delivered_at is not None
    # numbers never appear in the alert row
    assert all("+49" not in a.sent_to for a in alerts)


def test_whatsapp_channel_without_number_and_failed_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, nonum = uuid.uuid4(), uuid.uuid4()

    async def wa_config(session: Any, tenant_id: Any) -> WhatsAppConfig:
        return WhatsAppConfig(
            tenant_id=TENANT,
            enabled=True,
            phone_number_id="1",
            access_token="t",
            template_names={"sla_escalation": "x"},
            sms_fallback=True,
        )

    async def failing_wa(session: Any, settings: Any, config: Any, **kw: Any) -> str:
        return "WhatsApp Cloud API meldet HTTP 500."

    async def fake_gateway(session: Any, tenant_id: Any) -> None:
        return None

    async def failing_sms(gateway: Any, to: str, text: str) -> str:
        return "Kein SMS-Gateway."

    _patch_common(monkeypatch, {user: ("u@example.org", "+49170"), nonum: ("n@example.org", None)})
    monkeypatch.setattr(escalation, "get_whatsapp_config", wa_config)
    monkeypatch.setattr(escalation, "send_whatsapp", failing_wa)
    monkeypatch.setattr(escalation, "get_gateway", fake_gateway)
    monkeypatch.setattr(escalation, "send_sms", failing_sms)
    rule = SlaRule(channels_by_level={"2": ["whatsapp"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _Session(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            _clock(),
            rule,
            2,
            [user, nonum],
            None,
            None,
        )
    )
    by_user = {a.sent_to: a for a in alerts}
    assert by_user[str(user)].delivery_error == (
        "WhatsApp Cloud API meldet HTTP 500. SMS-Rückfall: Kein SMS-Gateway."
    )
    assert by_user[str(nonum)].delivery_error == "Keine Mobilnummer des Benutzers hinterlegt."
    assert all(a.delivered_at is None for a in alerts)


def test_whatsapp_channel_disabled_config(monkeypatch: pytest.MonkeyPatch) -> None:
    user = uuid.uuid4()

    async def wa_config(session: Any, tenant_id: Any) -> WhatsAppConfig:
        return WhatsAppConfig(tenant_id=TENANT, enabled=False)

    _patch_common(monkeypatch, {user: ("u@example.org", "+49170")})
    monkeypatch.setattr(escalation, "get_whatsapp_config", wa_config)
    rule = SlaRule(channels_by_level={"0": ["whatsapp"]})
    alerts = asyncio.run(
        escalation.escalate_level(
            _Session(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            _clock(),
            rule,
            0,
            [user],
            None,
            None,
        )
    )
    assert alerts[0].delivery_error == "WhatsApp nicht eingerichtet oder deaktiviert."


def test_internal_alert_falls_back_to_on_call_without_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duty = uuid.uuid4()
    _patch_common(monkeypatch, {})
    on_call = OnCallSchedule(tenant_id=TENANT, user_id=duty, phone=None)
    alerts = asyncio.run(
        escalation.escalate_level(
            _Session(),  # type: ignore[arg-type]
            make_settings(web_crm_url=None),
            _ticket(),
            _clock(),
            None,
            0,
            [],
            None,
            on_call,
        )
    )
    internal = [a for a in alerts if a.channel == AlertChannel.INTERNAL]
    assert [a.sent_to for a in internal] == [str(duty)]


def test_check_and_escalate_returns_colour_for_missing_ticket() -> None:
    """A breached clock whose ticket vanished yields its colour without escalation."""
    session = _Session(_calendar())
    now = datetime.now(UTC)
    clock = _clock(started_at=now - timedelta(hours=2), due_response_at=now - timedelta(minutes=1))
    color = asyncio.run(escalation.check_and_escalate(session, clock, make_settings()))  # type: ignore[arg-type]
    assert color == SlaColor.RED
    assert clock.state == ClockState.BREACHED
    assert clock.escalated_steps == []
