"""M25-03 / V13: invitation period and attendance channel, expected values by hand.
Meeting on 10.12.2026 with 3 weeks: latest dispatch 19.11.2026; invitation on 19.11. is in
time, on 20.11. it is short notice. With 2 weeks the latest dispatch is 26.11.2026."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

from mhvp.hoa import meeting_rules as rules

SCHEDULED = datetime(2026, 12, 10, 18, 0, tzinfo=UTC)


def test_latest_invitation_date_and_check() -> None:
    assert rules.latest_invitation_date(SCHEDULED, 3) == date(2026, 11, 19)
    assert rules.latest_invitation_date(date(2026, 12, 10), 2) == date(2026, 11, 26)
    assert rules.invitation_check(SCHEDULED, date(2026, 11, 19), 3) == (date(2026, 11, 19), False)
    assert rules.invitation_check(SCHEDULED, date(2026, 11, 20), 3) == (date(2026, 11, 19), True)
    assert rules.invitation_check(SCHEDULED, date(2026, 11, 26), 2) == (date(2026, 11, 26), False)


def _att(present: bool = False, online: bool = False, proxy: str | None = None) -> Any:
    return SimpleNamespace(present=present, online=online, proxy_contact_id=proxy)


def test_attendance_channel() -> None:
    assert rules.attendance_channel(None) == "absent"
    assert rules.attendance_channel(_att()) == "absent"
    assert rules.attendance_channel(_att(present=True)) == "presence"
    assert rules.attendance_channel(_att(present=True, online=True)) == "online"
    assert rules.attendance_channel(_att(proxy="x")) == "proxy"


def test_invitation_notice_and_short_notice_note() -> None:
    meeting = SimpleNamespace(
        mode="virtual",
        virtual_basis_valid_until=date(2029, 3, 1),
        scheduled_at=SCHEDULED,
        invited_at=date(2026, 11, 25),
        invitation_short_notice=True,
        invitation_short_notice_reason="Rohrbruch, Sanierung eilt",
    )
    basis = SimpleNamespace(number=7, decided_on=date(2026, 3, 1))
    notice = rules.invitation_notice(meeting, basis)  # type: ignore[arg-type]
    assert notice is not None
    assert "Beschluss Nr. 7 vom 01.03.2026, gültig bis 01.03.2029" in notice
    assert rules.invitation_notice(SimpleNamespace(mode="presence"), None) is None  # type: ignore[arg-type]
    hybrid = rules.invitation_notice(SimpleNamespace(mode="hybrid"), None)  # type: ignore[arg-type]
    assert hybrid is not None
    assert "hybride" in hybrid
    note = rules.short_notice_note(meeting, 3)  # type: ignore[arg-type]
    assert note is not None
    assert "25.11.2026" in note
    assert "19.11.2026" in note
    assert "Rohrbruch" in note
    meeting.invitation_short_notice = False
    assert rules.short_notice_note(meeting, 3) is None  # type: ignore[arg-type]
