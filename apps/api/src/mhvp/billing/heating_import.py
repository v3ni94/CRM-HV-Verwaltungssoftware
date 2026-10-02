"""External heating cost import of the metering service (M17-09, 6.5 ``heating_cost_import``,
rule H01, docs/rules/M17-09-heizkostenimport.md).

The metering service delivers the result per user number; this module stores it with the
original document, maps user numbers to unit and contract, checks the component sums against
the document total, checks the CO2 split with the existing step model of
``heating_calc.co2_split`` (no own step logic) and looks for a double capture in the invoice
book (same issuer, overlapping period). Only a checked import is fed into an operating cost
statement as one external heating item. CSV columns are mapped explicitly by the clerk; no
provider format is assumed (A, docs/ASSUMPTIONS.md)."""

import csv
import io
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import heating_calc, heating_services, services
from mhvp.billing.models import (
    HeatingCostImport,
    Statement,
    StatementCostItem,
    StatementHeating,
)
from mhvp.billing.status import StatementStatus
from mhvp.core.problems import ErrorCodes, ProblemError

COST_FIELDS = ("heating_base", "heating_consumption", "hot_water_base", "hot_water_consumption")
CO2_FIELDS = ("co2_landlord", "co2_tenant")
ROW_FIELDS = COST_FIELDS + CO2_FIELDS
CENT = Decimal("0.01")
MAX_CSV_ROWS = 5000


def _money(value: Any, label: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"{label}: keine Zahl.") from None
    if amount != amount.quantize(CENT, rounding=ROUND_HALF_UP):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"{label}: mehr als zwei Nachkommastellen."
        )
    if amount < 0:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"{label}: negativ.")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def normalise_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Rows as stored: user number plus the six components as strings with two decimals."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, r in enumerate(rows, start=1):
        number = str(r.get("user_number") or "").strip()
        if not number:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Zeile {i}: Nutzernummer fehlt.")
        if number in seen:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Zeile {i}: Nutzernummer {number} doppelt."
            )
        seen.add(number)
        entry = {"user_number": number}
        for f in ROW_FIELDS:
            entry[f] = str(_money(r.get(f, "0"), f"Zeile {i} {f}"))
        out.append(entry)
    return out


def _parse_amount(raw: str, decimal_comma: bool, label: str) -> str:
    text = raw.strip().replace(" ", "")
    if text == "":
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"{label}: Wert fehlt.")
    if decimal_comma:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"{label}: Komma ohne Einstellung Dezimalkomma."
        )
    return str(_money(text, label))


def parse_csv(
    content: str, *, delimiter: str, decimal_comma: bool, column_map: dict[str, str]
) -> list[dict[str, str]]:
    """Parse a CSV with an explicit column map {field: header}. Every field of ``ROW_FIELDS``
    and ``user_number`` must be mapped; no column is guessed (A)."""
    missing = [f for f in ("user_number", *ROW_FIELDS) if not column_map.get(f)]
    if missing:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Spaltenzuordnung fehlt für: {', '.join(missing)}."
        )
    reader = csv.DictReader(io.StringIO(content.lstrip("﻿")), delimiter=delimiter)
    headers = set(reader.fieldnames or [])
    unknown = sorted({h for h in column_map.values() if h not in headers})
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Spalten nicht in der Datei: {', '.join(unknown)}."
        )
    rows: list[dict[str, Any]] = []
    for line_no, record in enumerate(reader, start=2):
        if not any((v or "").strip() for v in record.values()):
            continue
        if len(rows) >= MAX_CSV_ROWS:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zu viele Zeilen.")
        entry: dict[str, Any] = {
            "user_number": (record.get(column_map["user_number"]) or "").strip()
        }
        for f in ROW_FIELDS:
            entry[f] = _parse_amount(
                record.get(column_map[f]) or "", decimal_comma, f"Zeile {line_no} {f}"
            )
        rows.append(entry)
    if not rows:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Datei enthält keine Datenzeilen.")
    return normalise_rows(rows)


def row_total(r: dict[str, str]) -> Decimal:
    return sum((Decimal(r[f]) for f in COST_FIELDS), Decimal("0.00"))


def sum_check(row: HeatingCostImport) -> dict[str, Any]:
    """Pure part of the check: components against the document total and the CO2 shares
    against each row and the stated CO2 costs. Returns totals and blocking findings."""
    findings: list[str] = []
    totals = {f: sum((Decimal(r[f]) for r in row.rows), Decimal("0.00")) for f in ROW_FIELDS}
    grand = sum((totals[f] for f in COST_FIELDS), Decimal("0.00"))
    if not row.rows:
        findings.append("Keine Kostenzeilen erfasst.")
    if grand != row.document_total:
        findings.append(
            f"Summe der Kostenbestandteile {grand} EUR weicht von der Belegsumme "
            f"{row.document_total} EUR ab (Differenz {grand - row.document_total} EUR)."
        )
    for r in row.rows:
        co2 = Decimal(r["co2_landlord"]) + Decimal(r["co2_tenant"])
        if co2 > row_total(r):
            findings.append(
                f"Nutzer {r['user_number']}: CO2-Anteile übersteigen die Heizkosten der Einheit."
            )
    co2_total = totals["co2_landlord"] + totals["co2_tenant"]
    stated = row.co2.get("costs")
    if stated is not None and Decimal(str(stated)) != co2_total:
        findings.append(
            f"CO2-Anteile je Einheit ({co2_total} EUR) ergeben nicht die CO2-Kosten "
            f"laut Beleg ({stated} EUR)."
        )
    return {
        "totals": {k: str(v) for k, v in totals.items()},
        "grand_total": str(grand),
        "co2_total": str(co2_total),
        "findings": findings,
    }


async def co2_check(
    session: AsyncSession, row: HeatingCostImport, co2_total: Decimal, landlord_total: Decimal
) -> dict[str, Any]:
    """Recompute the split with the existing step model and table (``heating_calc.co2_split``
    via ``heating_services.effective_tables``) and compare with the provider's landlord share.
    Per unit rounding of the provider is accepted up to one cent per row."""
    c = row.co2
    tables = await heating_services.effective_tables(session, row.period_from)
    inp = heating_calc.Co2Input(
        mode=c.get("mode", "apply"),
        building_kind=c.get("building_kind", "unknown"),
        costs=co2_total,
        emissions_kg=heating_services._dec(c.get("emissions_kg"), "co2.emissions_kg"),
        reference_area_m2=heating_services._dec(
            c.get("reference_area_m2"), "co2.reference_area_m2"
        ),
        reason=c.get("reason"),
        steps=heating_services.co2_steps_from_rows(tables["co2_steps"]["rows"]),
        steps_source=tables["co2_steps"]["source"],
    )
    try:
        split = heating_calc.co2_split(inp, (row.period_to - row.period_from).days + 1)
    except heating_calc.HeatingCalcError as exc:
        return {"status": "pruefen", "findings": [str(exc)]}
    findings: list[str] = []
    if split["status"] == "pruefen":
        findings.append("CO2-Aufteilung im Prüfstatus; Übernahme erst nach Klärung (D27).")
    elif split["status"] == "nicht_anwendbar":
        if landlord_total != 0:
            findings.append("CO2 als nicht anwendbar erklärt, aber Vermieteranteile erfasst.")
    else:
        expected = Decimal(split["landlord"])
        tolerance = CENT * max(len(row.rows), 1)
        if abs(expected - landlord_total) > tolerance:
            findings.append(
                f"CO2-Vermieteranteil laut Messdienst {landlord_total} EUR, nach Stufenmodell "
                f"{expected} EUR."
            )
    return split | {
        "findings": findings,
        "steps_review_status": tables["co2_steps"]["review_status"],
    }


async def mapping_check(session: AsyncSession, row: HeatingCostImport) -> list[str]:
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit

    findings: list[str] = []
    for r in row.rows:
        m = row.user_mapping.get(r["user_number"])
        if not m or not m.get("unit_id"):
            findings.append(f"Nutzer {r['user_number']}: keine Einheit zugeordnet.")
            continue
        unit = await session.get(Unit, uuid.UUID(str(m["unit_id"])))
        if unit is None or unit.property_id != row.property_id:
            findings.append(f"Nutzer {r['user_number']}: Einheit gehört nicht zum Objekt.")
            continue
        if m.get("contract_id"):
            contract = await session.get(Contract, uuid.UUID(str(m["contract_id"])))
            if (
                contract is None
                or contract.unit_id != unit.id
                or contract.kind is not ContractKind.TENANCY
            ):
                findings.append(
                    f"Nutzer {r['user_number']}: Vertrag ist kein Mietvertrag dieser Einheit."
                )
    return findings


async def duplicate_check(session: AsyncSession, row: HeatingCostImport) -> list[dict[str, Any]]:
    """Invoices of the same issuer whose service period (or, without one, the invoice date)
    overlaps the import period, and other imports of the property for an overlapping period
    from the same provider."""
    from mhvp.accounting.models import Invoice

    hits: list[dict[str, Any]] = []
    if row.provider_contact_id is not None:
        invoices = (
            await session.scalars(
                select(Invoice).where(Invoice.provider_contact_id == row.provider_contact_id)
            )
        ).all()
        for inv in invoices:
            start = inv.service_from or inv.invoice_date
            end = inv.service_to or inv.service_from or inv.invoice_date
            if start <= row.period_to and end >= row.period_from:
                hits.append(
                    {
                        "kind": "invoice",
                        "id": str(inv.id),
                        "number": inv.number,
                        "gross": str(inv.gross),
                        "service_from": None
                        if inv.service_from is None
                        else inv.service_from.isoformat(),
                        "service_to": None
                        if inv.service_to is None
                        else inv.service_to.isoformat(),
                    }
                )
    others = (
        await session.scalars(
            select(HeatingCostImport).where(
                HeatingCostImport.property_id == row.property_id,
                HeatingCostImport.id != row.id,
                HeatingCostImport.period_from <= row.period_to,
                HeatingCostImport.period_to >= row.period_from,
            )
        )
    ).all()
    for o in others:
        same = (
            o.provider_contact_id == row.provider_contact_id
            if row.provider_contact_id is not None
            else o.provider_name.strip().lower() == row.provider_name.strip().lower()
        )
        if same:
            hits.append({"kind": "heating_cost_import", "id": str(o.id), "status": o.status})
    return hits


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def reset(row: HeatingCostImport) -> None:
    if row.status == "applied":
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Übernommener Import ist gesperrt; Änderung nur neu."
        )
    row.status = "draft"
    row.check_result = None
    row.checked_by = None
    row.checked_at = None


async def check(
    session: AsyncSession,
    row: HeatingCostImport,
    user_id: uuid.UUID | None,
    duplicate_ack_reason: str | None,
) -> dict[str, Any]:
    reset(row)
    sums = sum_check(row)
    findings = list(sums["findings"])
    if row.document_id is None:
        findings.append("Originaldokument der Messdienstabrechnung fehlt.")
    findings += await mapping_check(session, row)
    co2 = await co2_check(
        session, row, Decimal(sums["co2_total"]), Decimal(sums["totals"]["co2_landlord"])
    )
    findings += co2["findings"]
    duplicates = await duplicate_check(session, row)
    if duplicates and not duplicate_ack_reason:
        findings.append(
            "Mögliche Doppelerfassung (Rechnungsbuch oder weiterer Import); Prüfung mit "
            "Begründung bestätigen."
        )
    row.duplicate_ack_reason = duplicate_ack_reason if duplicates else None
    result = sums | {"findings": findings, "co2": co2, "duplicates": duplicates}
    row.check_result = result
    if not findings:
        row.status = "checked"
        row.checked_by = user_id
        row.checked_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.flush()
    return result


async def _occupancy_keys(
    session: AsyncSession, statement: Statement, row: HeatingCostImport
) -> dict[str, Decimal]:
    occ = await services.occupants(session, statement)
    by_contract = {str(o["contract_id"]): o["key"] for o in occ if o["contract_id"]}
    vacancies: dict[str, list[str]] = {}
    for o in occ:
        if o["contract_id"] is None:
            vacancies.setdefault(str(o["unit_id"]), []).append(o["key"])
    amounts: dict[str, Decimal] = {}
    for r in row.rows:
        m = row.user_mapping[r["user_number"]]
        if m.get("contract_id"):
            key = by_contract.get(str(m["contract_id"]))
            if key is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Nutzer {r['user_number']}: Vertrag nicht im Abrechnungszeitraum.",
                )
        else:
            keys = vacancies.get(str(m["unit_id"]), [])
            if len(keys) != 1:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Nutzer {r['user_number']}: Leerstand der Einheit nicht eindeutig.",
                )
            key = keys[0]
        charge = row_total(r) - Decimal(r["co2_landlord"])
        amounts[key] = amounts.get(key, Decimal("0.00")) + charge
    return amounts


async def apply(
    session: AsyncSession, statement: Statement, row: HeatingCostImport, user_id: uuid.UUID | None
) -> StatementCostItem:
    """Feed a checked import as one external heating item. The landlord CO2 share stays with
    the landlord (not allocated, assumption A, open question M17-09-01)."""
    if row.status != "checked":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Übernahme nur nach erfolgreicher Prüfung."
        )
    if statement.status is not StatementStatus.DRAFT:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über eine neue Version änderbar."
        )
    if statement.property_id != row.property_id:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Abrechnung gehört zu anderem Objekt.")
    if (statement.period_from, statement.period_to) != (row.period_from, row.period_to):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Abrechnungszeitraum des Messdiensts weicht vom Abrechnungszeitraum ab.",
        )
    own = await session.scalar(
        select(StatementHeating).where(StatementHeating.statement_id == statement.id)
    )
    if own is not None and own.applied_item_id is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Abrechnung enthält bereits eine eigene Heizkostenposition."
        )
    existing = await session.scalar(
        select(HeatingCostImport).where(
            HeatingCostImport.statement_id == statement.id,
            HeatingCostImport.status == "applied",
        )
    )
    if existing is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Abrechnung enthält bereits einen Messdienstimport."
        )
    amounts = await _occupancy_keys(session, statement, row)
    total = sum(amounts.values(), Decimal("0.00"))
    item = StatementCostItem(
        tenant_id=statement.tenant_id,
        created_by=user_id,
        statement_id=statement.id,
        label=f"Heiz- und Warmwasserkosten (Messdienst {row.provider_name})"[:200],
        amount=total,
        external_amounts={k: str(v) for k, v in amounts.items()},
        basis=(
            f"Messdienstabrechnung {row.provider_name}, Zeitraum {row.period_from:%d.%m.%Y} bis "
            f"{row.period_to:%d.%m.%Y}, Import {row.id}, Originaldokument {row.document_id}; "
            "CO2-Vermieteranteil nicht umgelegt (H01, M17-09)."
        ),
        heating=True,
    )
    session.add(item)
    await session.flush()
    row.applied_item_id = item.id
    row.statement_id = statement.id
    row.status = "applied"
    row.applied_at = datetime.now(UTC)
    row.updated_by = user_id
    await session.flush()
    return item


def period_ok(period_from: date, period_to: date) -> None:
    if period_from > period_to:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum: Beginn nach Ende.")
