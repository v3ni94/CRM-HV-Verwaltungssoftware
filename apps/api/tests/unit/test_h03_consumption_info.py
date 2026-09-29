"""Rule H03 helpers without a database: due day, month arithmetic, tenant snapshot without
operator markers, averages and the beat entry."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from mhvp.billing import consumption_info as ci
from mhvp.billing.models import ConsumptionInfo
from mhvp.core.config import Settings
from mhvp.worker import create_celery


def test_first_working_day_and_month_arithmetic() -> None:
    assert ci.first_working_day(date(2025, 11, 15)) == date(2025, 11, 3)  # 1.11.2025 Saturday
    assert ci.first_working_day(date(2025, 10, 1)) == date(2025, 10, 1)  # Wednesday
    assert ci.first_working_day(date(2026, 2, 20)) == date(2026, 2, 2)  # 1.2.2026 Sunday
    assert ci.previous_month(date(2026, 1, 31)) == date(2025, 12, 1)
    assert ci.month_end(date(2024, 2, 10)) == date(2024, 2, 29)
    assert ci.month_label(date(2025, 8, 1)) == "08.2025"


def _values() -> dict[str, object]:
    return {
        "month": "2025-08-01",
        "heating": {"value": "1234.5", "unit_of_measure": "kWh", "kind": "actual", "source": "x"},
        "hot_water": {"value": "2.4", "unit_of_measure": "m3", "kind": "estimated", "source": "x"},
        "previous_month": None,
        "previous_year_month": {"heating": {"value": "1000", "unit_of_measure": "kWh"}},
        "property_average": {"heating": {"value": "900.00", "units": 3, "unit_of_measure": "kWh"}},
        "to_verify": list(ci.TO_VERIFY),
    }


def test_snapshot_rows_format_and_missing_values() -> None:
    rows = ci.snapshot_rows(_values())
    assert rows[0] == ["Heizung", "1.234,50 kWh", "keine Angabe", "1.000,00 kWh", "900,00 kWh"]
    assert rows[1][1] == "2,40 m3 (geschätzt)"
    assert rows[1][4] == "keine Angabe"


def test_render_html_has_no_operator_markers() -> None:
    html = ci.render_html(
        property_line="773 Haus", unit_number="01", month=date(2025, 8, 1), values=_values()
    )
    assert "Verbrauchsinformation 08.2025" in html
    assert "01.08.2025 bis 31.08.2025" in html
    assert "verifizieren" not in html
    assert "energy_mix" not in html
    assert "1.234,50 kWh" in html


def test_tenant_view_strips_operator_content() -> None:
    row = ConsumptionInfo(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        property_id=uuid.uuid4(),
        unit_id=uuid.uuid4(),
        month=date(2025, 8, 1),
        rule_version=ci.RULE_VERSION,
        values=_values(),
        data_basis={"metering_rows": {"heating": {"id": "secret"}}},
        missing=["hot_water_estimated", "no_unit_assignment"],
        snapshot_html="<p>x</p>",
        snapshot_hash="h",
        created_at=datetime.now(UTC),
    )
    tenant = ci.tenant_view(row, with_snapshot=True)
    assert "to_verify" not in tenant["values"]
    assert tenant["estimated"] == ["hot_water"]
    assert set(tenant) == {
        "id",
        "unit_id",
        "month",
        "values",
        "estimated",
        "created_at",
        "snapshot_html",
    }
    staff = ci.staff_view(row)
    assert staff["to_verify"][0]["status"] == "zu verifizieren"
    assert "Einheit beim Messdienst nicht zugeordnet" in staff["missing_labels"]


def test_average_ignores_missing_and_mixed_measures() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    values: dict[uuid.UUID, dict[str, Any]] = {
        a: {"heating": {"value": "100", "unit_of_measure": "kWh"}},
        b: {"heating": {"value": "50", "unit_of_measure": "kWh"}},
        c: {"heating": {"value": None, "unit_of_measure": "kWh"}},
    }
    assert ci._average(values, "heating") == {
        "value": "75.00",
        "units": 2,
        "unit_of_measure": "kWh",
    }
    assert ci._average({}, "heating") is None
    values[b]["heating"]["unit_of_measure"] = "MWh"
    mixed = ci._average(values, "heating")
    assert mixed is not None
    assert mixed["unit_of_measure"] is None
    assert Decimal(mixed["value"]) == Decimal("75.00")


def test_beat_entry(settings: Settings) -> None:
    entry = create_celery(settings).conf.beat_schedule["billing-consumption-info"]
    assert entry["task"] == "mhvp.billing.consumption_info"
    assert entry["schedule"].day_of_month == {1, 2, 3}
