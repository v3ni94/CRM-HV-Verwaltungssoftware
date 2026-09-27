"""Units, owners and tenants of one property as an Immoware24 unit list for objektakte (27.09.2026).

objektakte imports the list as an import proposal (endpoint ``objects/{number}/imports/``, scope
persons:write); nothing is taken over there before a person reviews and releases the rows in its
import assistant. From the release on, objektakte names the owner and tenant files and files CRM
uploads into them. The list carries unit numbers, labels, buildings and the names of the current
owners and tenants (``mhvp.objektakte.lists.persons_list``), never addresses, e-mail, phone, bank
data or amounts: the money columns of the format stay empty.
"""

from __future__ import annotations

import csv
import uuid
from io import StringIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.escaping import csv_safe_cell
from mhvp.objektakte import lists
from mhvp.properties.models import Building, ManagementType, Property, Unit

HEADER = (
    "Objekt-Nr",
    "Status",
    "Objekt",
    "Verwaltungsart",
    "Gebaeude",
    "VE-Nr",
    "VE-Beschreibung",
    "Lage",
    "Eigentuemer",
    "Hausgeld_EUR_mtl",
    "Mieter",
    "Miete_EUR_mtl",
)
MANAGEMENT = {
    ManagementType.HOA: "WEG",
    ManagementType.HOA_WITH_SEV: "WEG mit SEV",
    ManagementType.RENTAL: "Mietverwaltung",
}


def _names(rows: list[dict[str, object]]) -> dict[str, str]:
    by_unit: dict[str, list[str]] = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        if name:
            names = by_unit.setdefault(str(row["unit_id"]), [])
            if name not in names:
                names.append(name)
    return {unit_id: " und ".join(names) for unit_id, names in by_unit.items()}


async def unit_list_csv(
    session: AsyncSession, tenant_id: uuid.UUID, prop: Property
) -> tuple[bytes, dict[str, int]]:
    """CSV (UTF-8, semicolon) of every unit of the property with its current owners and tenants."""
    owners = _names((await lists.persons_list(session, tenant_id, prop, "owners"))["rows"])
    tenants = _names((await lists.persons_list(session, tenant_id, prop, "tenants"))["rows"])
    units = (
        await session.execute(
            select(Unit, Building.name)
            .outerjoin(Building, Building.id == Unit.building_id)
            .where(Unit.tenant_id == tenant_id, Unit.property_id == prop.id)
            .order_by(Unit.number)
        )
    ).all()
    out = StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\n")
    writer.writerow(HEADER)
    for unit, building in units:
        key = str(unit.id)
        writer.writerow(
            [
                csv_safe_cell(v)
                for v in (
                    prop.number,
                    "aktiv",
                    prop.name,
                    MANAGEMENT.get(prop.management_type, ""),
                    building or "",
                    unit.number,
                    unit.label or "",
                    "",
                    owners.get(key, ""),
                    "",
                    tenants.get(key, ""),
                    "",
                )
            ]
        )
    counts = {
        "units": len(units),
        "units_with_owner": sum(1 for u, _ in units if str(u.id) in owners),
        "units_with_tenant": sum(1 for u, _ in units if str(u.id) in tenants),
    }
    return out.getvalue().encode("utf-8"), counts
