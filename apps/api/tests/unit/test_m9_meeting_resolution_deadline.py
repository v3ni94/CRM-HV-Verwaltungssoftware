"""M9-07: resolution deadline of virtual owners' meetings in the deadline list (A41)."""

from datetime import date

import pytest

from mhvp.core.problems import ProblemError
from mhvp.hoa.meetings import MeetingPatch, validate_resolution_deadline
from mhvp.workspace import jobs


def test_deadline_with_source_on_virtual_meeting_is_valid() -> None:
    validate_resolution_deadline("virtual", date(2026, 11, 30), "Beschluss TOP 3 vom 01.06.2026")


def test_no_deadline_no_source_is_valid() -> None:
    validate_resolution_deadline("presence", None, None)


@pytest.mark.parametrize("source", [None, "", "  ", "ab"])
def test_deadline_requires_source(source: str | None) -> None:
    with pytest.raises(ProblemError):
        validate_resolution_deadline("virtual", date(2026, 11, 30), source)


@pytest.mark.parametrize("mode", ["presence", "hybrid"])
def test_deadline_only_for_virtual_meetings(mode: str) -> None:
    with pytest.raises(ProblemError):
        validate_resolution_deadline(mode, date(2026, 11, 30), "GO § 12 Abs. 2")


def test_source_without_deadline_is_rejected() -> None:
    with pytest.raises(ProblemError):
        validate_resolution_deadline("virtual", None, "GO § 12 Abs. 2")


def test_patch_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="extra"):
        MeetingPatch.model_validate({"mode": "virtual"})


def test_deadline_kind_registered_with_permissions() -> None:
    assert jobs.MEETING_RESOLUTION_KIND in jobs.DEADLINE_KINDS
    assert jobs.DEADLINE_PERMISSIONS[jobs.MEETING_RESOLUTION_KIND] == (
        "accounting:read",
        "accounting:update",
    )


def test_fixed_lead_time_of_seven_days() -> None:
    assert jobs.lead_days_for(jobs.MEETING_RESOLUTION_KIND, 30) == 7
    assert jobs.lead_days_for("contract_end", 30) == 30


def test_reference_marks_orientation_and_source() -> None:
    ref = jobs.meeting_deadline_reference(date(2026, 10, 15), "GO § 12 Abs. 2")
    assert ref == (
        "Beschlussfrist virtuelle Versammlung vom 15.10.2026 "
        "(Orientierung, zu prüfen; Quelle: GO § 12 Abs. 2)"
    )
