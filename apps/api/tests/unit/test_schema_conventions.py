"""GAI-107: schema conventions over ``Base.metadata`` (master prompt 4.1, 6.9.8, E08).

* primary keys are a single UUID column (4.1, IDs UUID v7),
* timestamps are ``TIMESTAMPTZ`` (4.1), no float columns (rule 10, 6.9.8),
* money is ``NUMERIC(14,2)``, ratios and intermediate values ``NUMERIC(20,8)`` (6.9.8),
* every table carries ``tenant_id`` unless it is a registered platform table (5.3).

Existing deviations are listed below with their reason. The lists are exact: a new deviation
fails the test, and a fixed one fails until its entry is removed. Changing a column type is a
migration and outside this test (AJ19 writes none); the RLS side of tenant tables is checked
against the database in tests/integration/test_rls.py.
"""

from sqlalchemy import DateTime, Float, Numeric, Table, Uuid

import mhvp.models  # noqa: F401  (registers every model on the metadata)
from mhvp.core.db.base import Base

ALLOWED_NUMERIC = frozenset({(14, 2), (20, 8)})

# Natural or composite keys kept on purpose.
PK_EXCEPTIONS: dict[str, str] = {
    "rent_law_rule": "catalogue keyed by its rule code (platform data, no tenant)",
    "journal_number_counter": "gapless counter per ledger and fiscal year (composite key)",
}

# (table.column) -> (precision, scale, reason). Units and percentages that are neither a
# booking amount nor a calculation intermediate; a change needs a migration (open point AJ19).
NUMERIC_EXCEPTIONS: dict[str, tuple[int, int, str]] = {
    "unit.rooms": (4, 1, "room count, NUMERIC(4,1) in the unit model of section 6"),
    "listing.rooms": (4, 1, "room count of the listing, same as unit.rooms"),
    "listing.living_area_sqm": (10, 2, "advertised area for the portal export, not a ratio"),
    "listing.energy_value": (8, 2, "energy certificate value as printed, not a calculation"),
    "rent_index_entry.area_from_sqm": (10, 2, "area band bound from the rent index table"),
    "rent_index_entry.area_to_sqm": (10, 2, "area band bound from the rent index table"),
    "rent_increase_case.living_area_sqm": (10, 2, "area as documented in the case, display"),
    "property.latitude": (10, 7, "geo coordinate, not a domain amount"),
    "property.longitude": (10, 7, "geo coordinate, not a domain amount"),
    "deposit_interest_reference_rate.rate": (8, 5, "published interest rate as given"),
    "deposit_interest_rate.rate": (8, 5, "interest rate as given"),
    "deposit_interest_draft.rate": (8, 5, "rate copied from deposit_interest_rate"),
    "statement_advance_rule.surcharge_percent": (5, 2, "configured percentage input"),
    "statement_advance_proposal.surcharge_percent": (5, 2, "percentage copied from the rule"),
    "onboarding_match_setting.link_threshold": (4, 2, "matching score threshold 0 to 1"),
    "onboarding_match_setting.suggest_threshold": (4, 2, "matching score threshold 0 to 1"),
    "objektakte_classification_rule.confidence": (4, 3, "AI confidence score, no money"),
    "bank_rule_proposal.evidence_count": (6, 1, "evidence counter, no money"),
    "bank_rule_proposal.rejected_evidence_count": (6, 1, "evidence counter, no money"),
    "objektakte_ai_call.cost_eur": (12, 6, "provider cost per call below one cent, statistics"),
    "objektakte_party_assignment.share": (9, 6, "ownership share; candidate for (20,8)"),
    "handover_meter.value": (14, 3, "meter reading with three decimals as read on site"),
}

# Tables without tenant_id: platform administration or global catalogues (5.3, ADR 0006).
PLATFORM_TABLES: dict[str, str] = {
    "tenant": "the tenant itself",
    "app_user": "users exist before and across memberships",
    "webauthn_credential": "credential of a platform user",
    "oidc_client": "platform OIDC client registry",
    "platform_audit_event": "platform audit trail",
    "platform_availability_measurement": "platform operations",
    "platform_availability_month": "platform operations",
    "platform_availability_probe_point": "platform operations",
    "platform_maintenance_window": "platform operations",
    "platform_scale_setting": "platform operations",
    "platform_scale_snapshot": "platform operations",
    "platform_settings": "platform operations",
    "price_list_entry": "platform price list",
    "pricing_plan_item": "platform price list",
    "rent_cap_area": "global catalogue of regulated areas",
    "rent_law_rule": "global legal rule catalogue",
}


def _tables() -> list[Table]:
    return list(Base.metadata.tables.values())


def test_metadata_is_populated() -> None:
    assert len(_tables()) > 300


def test_primary_keys_are_single_uuid_columns() -> None:
    bad = []
    for table in _tables():
        cols = list(table.primary_key.columns)
        ok = len(cols) == 1 and isinstance(cols[0].type, Uuid)
        if not ok and table.name not in PK_EXCEPTIONS:
            bad.append(table.name)
        if ok and table.name in PK_EXCEPTIONS:
            bad.append(f"{table.name} (stale exception)")
    assert bad == []


def test_timestamps_are_timezone_aware_and_no_float_columns() -> None:
    naive, floats = [], []
    for table in _tables():
        for col in table.columns:
            if isinstance(col.type, DateTime) and not col.type.timezone:
                naive.append(f"{table.name}.{col.name}")
            if isinstance(col.type, Float):
                floats.append(f"{table.name}.{col.name}")
    assert naive == []
    assert floats == []


def test_numeric_columns_use_the_decided_precisions() -> None:
    found: dict[str, tuple[int | None, int | None]] = {}
    for table in _tables():
        for col in table.columns:
            if isinstance(col.type, Numeric) and not isinstance(col.type, Float):
                found[f"{table.name}.{col.name}"] = (col.type.precision, col.type.scale)
    deviating = {k: v for k, v in found.items() if v not in ALLOWED_NUMERIC}
    expected = {k: (p, s) for k, (p, s, _) in NUMERIC_EXCEPTIONS.items()}
    assert deviating == expected


def test_tables_without_tenant_id_are_registered_platform_tables() -> None:
    without = {t.name for t in _tables() if "tenant_id" not in t.c}
    assert without == set(PLATFORM_TABLES)


def test_exception_lists_carry_reasons() -> None:
    reasons = [
        *PK_EXCEPTIONS.values(),
        *(r for _, _, r in NUMERIC_EXCEPTIONS.values()),
        *PLATFORM_TABLES.values(),
    ]
    assert all(r.strip() for r in reasons)
