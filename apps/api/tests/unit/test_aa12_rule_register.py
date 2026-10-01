"""AA12: register entry selection by settlement period (GA08-05), draft check points."""

from datetime import date

from mhvp.accounting import rule_register as rr
from mhvp.accounting.models import RuleVersion


def _rv(
    version: int, start: date, end: date | None = None, status: str = "confirmed"
) -> RuleVersion:
    return RuleVersion(
        rule_id="x", version=version, title="t", effective_from=start, effective_to=end,
        status=status,
    )  # fmt: skip


def test_period_start_selects_version_not_today() -> None:
    rows = [_rv(1, date(2020, 1, 1), date(2026, 12, 31)), _rv(2, date(2027, 1, 1))]
    assert rr.select_version(rows, date(2026, 1, 1)).version == 1  # type: ignore[union-attr]
    assert rr.select_version(rows, date(2027, 1, 1)).version == 2  # type: ignore[union-attr]
    assert rr.select_version(rows, date(2019, 12, 31)) is None


def test_withdrawn_is_skipped_and_reference_kept() -> None:
    rows = [_rv(1, date(2020, 1, 1)), _rv(2, date(2025, 1, 1), status="withdrawn")]
    picked = rr.select_version(rows, date(2026, 6, 1))
    assert picked is not None
    assert picked.version == 1
    ref = rr.snapshot_reference(picked)
    assert ref == {
        "id": None,
        "rule_id": "x",
        "version": 1,
        "status": "confirmed",
        "effective_from": "2020-01-01",
    }
    assert rr.snapshot_reference(None) is None


def test_checkpoints_are_drafts_without_invented_legal_values() -> None:
    ids = {c.rule_id for c in rr.CHECKPOINTS}
    assert ids == {"H03-HeizkostenV-5", "H03-HeizkostenV-12", "H05-CO2KostAufG-5a-5d"}
    assert all("Entwurf" in c.source_status and "Hinweis ohne Rechtsfolge" in c.note
               for c in rr.CHECKPOINTS)  # fmt: skip
    years = sorted(c.effective_from.year for c in rr.CHECKPOINTS if c.effective_from)
    assert years == [2028, 2029]
