"""AP04 / GAL-102: money NUMERIC(14,2), everything else that is computed NUMERIC(20,8) (6.9.8).

Other precisions are allowed only for the listed non computational values; the list may only
shrink.
"""

import importlib
import pkgutil

from sqlalchemy import Numeric

import mhvp
from mhvp.core.db.base import Base

ALLOWED = {(14, 2), (20, 8)}
# Not money, not an allocation basis: counters, rooms, energy value of a listing, geo
# coordinates, AI cost and confidence thresholds.
ALLOWLIST = {
    "bank_rule_proposal.evidence_count",
    "bank_rule_proposal.rejected_evidence_count",
    "listing.energy_value",
    "listing.rooms",
    "objektakte_ai_call.cost_eur",
    "objektakte_classification_rule.confidence",
    "onboarding_match_setting.link_threshold",
    "onboarding_match_setting.suggest_threshold",
    "property.latitude",
    "property.longitude",
    "unit.rooms",
}


def _numeric_columns() -> dict[str, tuple[int | None, int | None]]:
    for info in pkgutil.walk_packages(mhvp.__path__, "mhvp."):
        try:
            importlib.import_module(info.name)
        except Exception:  # noqa: S112 (optional modules)
            continue
    found: dict[str, tuple[int | None, int | None]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Numeric):
                found[f"{table.name}.{column.name}"] = (column.type.precision, column.type.scale)
    return found


def test_numeric_precisions_follow_698() -> None:
    offenders = {name for name, kind in _numeric_columns().items() if kind not in ALLOWED}
    assert offenders <= ALLOWLIST, sorted(offenders - ALLOWLIST)


def test_gal102_columns_are_20_8() -> None:
    found = _numeric_columns()
    for name in (
        "rent_increase_case.living_area_sqm",
        "listing.living_area_sqm",
        "rent_index_entry.area_from_sqm",
        "handover_meter.value",
        "objektakte_party_assignment.share",
        "deposit_interest_rate.rate",
        "statement_advance_rule.surcharge_percent",
    ):
        assert found[name] == (20, 8), name
