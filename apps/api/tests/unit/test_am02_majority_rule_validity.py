"""AM02 / GAJ-601, GAJ-604: validity of the meeting majority rule (helper and schema)."""

from __future__ import annotations

import uuid
from datetime import UTC, date

import pytest
from pydantic import ValidationError

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.meetings import MajorityRuleIn, _ensure_rule_in_force
from mhvp.hoa.models import MajorityRule


def _rule(valid_from: date, valid_to: date | None) -> MajorityRule:
    return MajorityRule(label="Testregel", valid_from=valid_from, valid_to=valid_to)


def test_rule_in_force_on_bounds() -> None:
    rule = _rule(date(2026, 1, 1), date(2026, 6, 20))
    _ensure_rule_in_force(rule, date(2026, 1, 1))
    _ensure_rule_in_force(rule, date(2026, 6, 20))
    _ensure_rule_in_force(_rule(date(2020, 1, 1), None), date(2030, 1, 1))


@pytest.mark.parametrize("day", [date(2025, 12, 31), date(2026, 6, 21)])
def test_rule_outside_validity_refused(day: date) -> None:
    with pytest.raises(ProblemError) as exc:
        _ensure_rule_in_force(_rule(date(2026, 1, 1), date(2026, 6, 20)), day)
    assert exc.value.error == ErrorCodes.HOA_MAJORITY_RULE_NOT_IN_FORCE


def test_schema_refuses_valid_to_before_valid_from() -> None:
    base = {
        "legal_entity_id": str(uuid.uuid4()),
        "label": "Testregel",
        "principle": "head",
        "share_of_votes_cast": "0.5",
        "source": "Testannahme",
        "valid_from": "2026-01-01",
    }
    MajorityRuleIn.model_validate(base | {"valid_to": "2026-01-01"})
    with pytest.raises(ValidationError):
        MajorityRuleIn.model_validate(base | {"valid_to": "2025-12-31"})


def test_an06_unapproved_rule_refused_approved_or_legacy_rule_usable() -> None:
    """AN06 / GAJ-602: a rule created under the four eyes switch applies only after approval;
    rules without requires_approval keep the behaviour before AN06."""
    from mhvp.hoa.meetings import _ensure_rule_usable

    day = date(2026, 6, 20)
    draft = _rule(date(2020, 1, 1), None)
    draft.requires_approval = True
    draft.approved_by = None
    with pytest.raises(ProblemError) as exc:
        _ensure_rule_usable(draft, day)
    assert exc.value.error == ErrorCodes.HOA_MAJORITY_RULE_NOT_APPROVED
    draft.approved_by = uuid.uuid4()
    _ensure_rule_usable(draft, day)
    legacy = _rule(date(2020, 1, 1), None)
    legacy.requires_approval = False
    _ensure_rule_usable(legacy, day)


def test_an06_meeting_day_is_business_date_not_utc() -> None:
    """AN14-09: a meeting at 00:30 Berlin time on 21.06.2026 is 22:30 UTC on 20.06.2026; the
    rule check uses the business date 21.06.2026."""
    from datetime import datetime, timedelta, timezone

    from mhvp.hoa.meetings import _ensure_rule_usable, meeting_day
    from mhvp.hoa.models import Meeting

    at = datetime(2026, 6, 21, 0, 30, tzinfo=timezone(timedelta(hours=2)))
    meeting = Meeting(scheduled_at=at.astimezone(UTC))
    assert meeting_day(meeting) == date(2026, 6, 21)
    rule = _rule(date(2026, 6, 21), None)
    rule.requires_approval = False
    _ensure_rule_usable(rule, meeting_day(meeting))
