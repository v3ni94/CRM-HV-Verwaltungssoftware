"""Lernphase Immoware24 (M33): Scanner und Differ als reine Funktionen auf synthetischen
Spiegeldaten, Uebernahme des Moduls Learning aus dem Immoware Hub."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from mhvp.immoware.learning import (
    compute_caldav_facts,
    compute_carddav_facts,
    compute_webdav_facts,
    diff_facts,
)
from mhvp.immoware.models import LearningKind


@dataclass
class FakeDocument:
    href: str
    is_collection: bool
    depth: int
    display_name: str | None = None
    size: int | None = None


@dataclass
class FakeContact:
    id: str
    fn: str | None = None
    org: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    addresses: list[dict] = field(default_factory=list)


@dataclass
class FakeEvent:
    summary: str | None = None
    location: str | None = None
    description: str | None = None
    dtstart: datetime | None = None
    dtend: datetime | None = None


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class TestComputeWebdavFacts:
    def test_counts_files_and_extensions_per_folder(self) -> None:
        rows = [
            FakeDocument(href="/123 Musterstrasse/", is_collection=True, depth=1),
            FakeDocument(
                href="/123 Musterstrasse/rechnung.pdf",
                is_collection=False,
                depth=2,
                display_name="rechnung.pdf",
                size=2048,
            ),
            FakeDocument(
                href="/123 Musterstrasse/foto.jpg",
                is_collection=False,
                depth=2,
                display_name="foto.jpg",
                size=512,
            ),
            FakeDocument(href="/sonstiges/", is_collection=True, depth=1),
        ]

        facts = compute_webdav_facts(rows)

        assert facts["folder_count"] == 2
        object_folder = next(f for f in facts["folders"] if f["path"] == "/123 Musterstrasse/")
        assert object_folder["file_count"] == 2
        assert object_folder["total_bytes"] == 2560
        assert object_folder["extensions"] == {"pdf": 1, "jpg": 1}
        assert object_folder["has_object_number"] is True
        assert facts["extension_totals"] == {"pdf": 1, "jpg": 1}
        assert facts["object_number_share"] == 1 / 2

    def test_empty_mirror_yields_zero_share(self) -> None:
        facts = compute_webdav_facts([])
        assert facts["folder_count"] == 0
        assert facts["object_number_share"] == 0.0


class TestComputeCarddavFacts:
    def test_field_usage_and_shares(self) -> None:
        rows = [
            FakeContact(
                id="1", fn="Erika Musterfrau", emails=["erika@example.com"], phones=["+49301234567"]
            ),
            FakeContact(id="2", org="Musterfrau GmbH", emails=[]),
            FakeContact(id="3"),
        ]

        facts = compute_carddav_facts(rows)

        assert facts["mirrored_contacts"] == 3
        assert facts["field_usage"]["fn"] == 1
        assert facts["field_usage"]["org"] == 1
        assert facts["field_usage"]["emails"] == 1
        assert facts["share_with_email"] == 1 / 3
        assert facts["duplicate_candidates"] == []

    def test_duplicate_candidates_by_normalized_email(self) -> None:
        rows = [
            FakeContact(id="1", fn="A", emails=["Erika@Example.com"]),
            FakeContact(id="2", fn="B", emails=["erika@example.com "]),
        ]

        facts = compute_carddav_facts(rows)

        assert len(facts["duplicate_candidates"]) == 1
        assert facts["duplicate_candidates"][0]["contact_ids"] == ["1", "2"]

    def test_empty_mirror(self) -> None:
        facts = compute_carddav_facts([])
        assert facts["mirrored_contacts"] == 0
        assert facts["share_with_email"] == 0.0


class TestComputeCaldavFacts:
    def test_field_usage_and_all_day_share(self) -> None:
        rows = [
            FakeEvent(
                summary="Eigentuemerversammlung",
                dtstart=_dt(2026, 3, 1, 9, 0),
                dtend=_dt(2026, 3, 1, 11, 0),
            ),
            FakeEvent(
                summary="Uebergabe Wohnung 3",
                dtstart=_dt(2026, 3, 5, 0, 0),
                dtend=_dt(2026, 3, 6, 0, 0),
            ),
        ]

        facts = compute_caldav_facts(rows)

        assert facts["mirrored_events"] == 2
        assert facts["field_usage"]["summary"] == 2
        assert facts["field_usage"]["location"] == 0
        assert facts["all_day_share"] == 1 / 2
        assert facts["top_summary_prefixes"][0]["prefix"] in {"Eigentuemerversammlung", "Uebergabe"}

    def test_events_per_month_ignores_older_than_12_months(self) -> None:
        rows = [FakeEvent(summary="Alt", dtstart=_dt(2000, 1, 1), dtend=_dt(2000, 1, 1))]
        facts = compute_caldav_facts(rows)
        assert facts["events_per_month"] == {}

    def test_empty_mirror(self) -> None:
        facts = compute_caldav_facts([])
        assert facts["mirrored_events"] == 0
        assert facts["all_day_share"] == 0.0


class TestDiffFacts:
    def test_first_run_has_no_previous(self) -> None:
        result = diff_facts(LearningKind.WEBDAV, None, {"folders": []})
        assert result["changed"] is True
        assert result["first_run"] is True

    def test_webdav_detects_new_and_removed_folders(self) -> None:
        previous = {"folders": [{"path": "/a/"}, {"path": "/b/"}], "extension_totals": {"pdf": 1}}
        current = {
            "folders": [{"path": "/a/"}, {"path": "/c/"}],
            "extension_totals": {"pdf": 1, "jpg": 2},
        }

        result = diff_facts(LearningKind.WEBDAV, previous, current)

        assert result["changed"] is True
        assert result["new_folders"] == ["/c/"]
        assert result["removed_folders"] == ["/b/"]
        assert result["new_extensions"] == ["jpg"]
        assert result["changes"]

    def test_webdav_unchanged(self) -> None:
        previous = {"folders": [{"path": "/a/"}], "extension_totals": {"pdf": 1}}
        current = {"folders": [{"path": "/a/"}], "extension_totals": {"pdf": 1}}
        result = diff_facts(LearningKind.WEBDAV, previous, current)
        assert result["changed"] is False
        assert result["changes"] == []

    def test_carddav_detects_newly_used_field(self) -> None:
        previous = {"field_usage": {"fn": 2, "org": 0}, "mirrored_contacts": 2}
        current = {"field_usage": {"fn": 2, "org": 1}, "mirrored_contacts": 2}

        result = diff_facts(LearningKind.CARDDAV, previous, current)

        assert result["changed"] is True
        assert result["newly_used_fields"] == ["org"]
        assert result["no_longer_used_fields"] == []

    def test_caldav_detects_no_longer_used_field_and_count_change(self) -> None:
        previous = {"field_usage": {"location": 3}, "mirrored_events": 5}
        current = {"field_usage": {"location": 0}, "mirrored_events": 4}

        result = diff_facts(LearningKind.CALDAV, previous, current)

        assert result["changed"] is True
        assert result["no_longer_used_fields"] == ["location"]
        assert result["count_before"] == 5
        assert result["count_after"] == 4
