"""CSV import and export of property assignments (master prompt section 6).

Numbers stay text (leading zeros preserved), external content is neutralised against
spreadsheet formulas on export (``csv_safe_cell``), a preview validates every row with an error
report and duplicate protection, and nothing is stored by uploading a file alone: ``apply`` is
a separate, deliberate call that re-validates and refuses the whole file on any error.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.escaping import csv_safe_cell
from mhvp.metering import services
from mhvp.metering.models import (
    MeteringConnection,
    MeteringExternalBillingUnit,
    MeteringPropertyAssignment,
    ServiceScope,
)
from mhvp.properties.models import Property

DELIMITER = ";"
COLUMNS: tuple[str, ...] = (
    "property_number",
    "connection_name",
    "external_number",
    "service_scope",
    "valid_from",
    "valid_to",
    "external_name",
    "external_address",
    "expected_unit_count",
    "note",
)
MAX_ROWS = 5000


@dataclass
class RowResult:
    line: int
    status: str  # ok | error | duplicate
    messages: list[str] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)
    property_id: uuid.UUID | None = None
    connection_id: uuid.UUID | None = None


@dataclass
class Preview:
    rows: list[RowResult]

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "error")

    @property
    def duplicate_count(self) -> int:
        return sum(1 for r in self.rows if r.status == "duplicate")


def template() -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=DELIMITER, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    writer.writerow(
        [
            "007",
            "Beispielanbieter Hauptkonto",
            "0004711",
            "heating",
            "2026-01-01",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    return out.getvalue()


def _parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return date.fromisoformat(value) if fmt == "%Y-%m-%d" else _de(value)
        except ValueError:
            continue
    raise ValueError(value)


def _de(value: str) -> date:
    d, m, y = value.split(".")
    return date(int(y), int(m), int(d))


def parse(content: str) -> list[dict[str, str]]:
    text = content.lstrip("﻿")
    sample = text[:2048]
    delimiter = DELIMITER
    if sample and sample.count(",") > sample.count(";"):
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    missing = [
        c
        for c in (
            "property_number",
            "connection_name",
            "external_number",
            "service_scope",
            "valid_from",
        )
        if c not in (reader.fieldnames or [])
    ]
    if missing:
        raise ValueError("Fehlende Spalten: " + ", ".join(missing))
    rows = []
    for row in reader:
        rows.append({k: (v or "").strip() for k, v in row.items() if k})
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Mehr als {MAX_ROWS} Zeilen.")
    return rows


async def preview(session: AsyncSession, tenant_id: uuid.UUID, content: str) -> Preview:
    try:
        raw_rows = parse(content)
    except ValueError as exc:
        return Preview(rows=[RowResult(line=1, status="error", messages=[str(exc)])])
    properties = {p.number: p for p in await session.scalars(select(Property))}
    connections = {c.display_name: c for c in await session.scalars(select(MeteringConnection))}
    seen: set[tuple[str, str, str, str, str]] = set()
    results: list[RowResult] = []
    for index, values in enumerate(raw_rows, start=2):
        result = RowResult(line=index, status="ok", values=values)
        prop = properties.get(values.get("property_number", ""))
        if prop is None:
            result.messages.append("Objektnummer unbekannt.")
        else:
            result.property_id = prop.id
        connection = connections.get(values.get("connection_name", ""))
        if connection is None:
            result.messages.append("Verbindung unbekannt (Anzeigename).")
        else:
            result.connection_id = connection.id
        if not values.get("external_number"):
            result.messages.append("Externe Nummer fehlt.")
        scope = values.get("service_scope", "")
        if scope not in {s.value for s in ServiceScope}:
            result.messages.append("Leistungsbereich ungültig.")
        valid_from: date | None = None
        valid_to: date | None = None
        try:
            valid_from = _parse_date(values.get("valid_from", ""))
            if valid_from is None:
                result.messages.append("Gültig ab fehlt.")
        except ValueError:
            result.messages.append("Gültig ab ungültig (JJJJ-MM-TT oder TT.MM.JJJJ).")
        try:
            valid_to = _parse_date(values.get("valid_to", ""))
        except ValueError:
            result.messages.append("Gültig bis ungültig.")
        if valid_from and valid_to and valid_to < valid_from:
            result.messages.append("Gültig bis liegt vor Gültig ab.")
        count = values.get("expected_unit_count", "")
        if count and not count.isdigit():
            result.messages.append("Erwartete Einheiten muss eine ganze Zahl sein.")
        if result.messages:
            result.status = "error"
            results.append(result)
            continue
        if prop is None or connection is None or valid_from is None:  # pragma: no cover
            continue
        key = (
            values["property_number"],
            values["connection_name"],
            values["external_number"],
            scope,
            valid_from.isoformat(),
        )
        if key in seen:
            result.status = "duplicate"
            result.messages.append("Doppelte Zeile in der Datei.")
            results.append(result)
            continue
        seen.add(key)
        existing = await session.scalar(
            select(MeteringPropertyAssignment)
            .join(
                MeteringExternalBillingUnit,
                MeteringExternalBillingUnit.id
                == MeteringPropertyAssignment.external_billing_unit_id,
            )
            .where(
                MeteringPropertyAssignment.property_id == prop.id,
                MeteringPropertyAssignment.connection_id == connection.id,
                MeteringExternalBillingUnit.external_number == values["external_number"],
                MeteringPropertyAssignment.service_scope == scope,
                MeteringPropertyAssignment.valid_from == valid_from,
            )
        )
        if existing is not None:
            result.status = "duplicate"
            result.messages.append(f"Zuordnung existiert bereits ({existing.id}).")
            results.append(result)
            continue
        candidate = MeteringPropertyAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            connection_id=connection.id,
            property_id=prop.id,
            external_billing_unit_id=uuid.uuid4(),
            service_scope=scope,
            valid_from=valid_from,
            valid_to=valid_to,
            unit_scope=[],
        )
        # The candidate's billing unit id is unknown before creation; the conflict check on the
        # same property and scope is what matters for an import row.
        conflicts = await services._conflicting_assignments(session, candidate)
        if conflicts:
            result.status = "error"
            result.messages.append(conflicts[0][1])
        results.append(result)
    return Preview(rows=results)


async def apply(
    session: AsyncSession, *, tenant_id: uuid.UUID, actor: uuid.UUID | None, content: str
) -> tuple[Preview, list[MeteringPropertyAssignment]]:
    """Re-validates and creates assignments (origin ``import``, status ``open``) only when
    no row has an error. Duplicates are skipped, never merged."""
    result = await preview(session, tenant_id, content)
    if result.error_count:
        from mhvp.core.problems import ErrorCodes, ProblemError

        raise ProblemError(
            ErrorCodes.METERING_IMPORT_INVALID,
            extensions={"error_count": result.error_count},
        )
    created: list[MeteringPropertyAssignment] = []
    for row in result.rows:
        if row.status != "ok":
            continue
        if row.property_id is None or row.connection_id is None:  # pragma: no cover
            continue
        values = row.values
        created.append(
            await services.create_assignment(
                session,
                tenant_id=tenant_id,
                actor=actor,
                connection_id=row.connection_id,
                property_id=row.property_id,
                external_number=values["external_number"],
                service_scope=values["service_scope"],
                valid_from=_parse_date(values["valid_from"]) or date.min,
                valid_to=_parse_date(values.get("valid_to", "")),
                origin="import",
                external_name=values.get("external_name") or None,
                external_address=values.get("external_address") or None,
                expected_unit_count=int(values["expected_unit_count"])
                if values.get("expected_unit_count")
                else None,
                note=values.get("note") or None,
            )
        )
    return result, created


def export(rows: list[dict[str, Any]]) -> str:
    """Rows are dicts with the COLUMNS keys plus status/id; every cell is written as text."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=DELIMITER, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    header = (*COLUMNS, "status", "assignment_id")
    writer.writerow(header)
    for row in rows:
        writer.writerow(
            [csv_safe_cell("" if row.get(c) is None else str(row.get(c))) for c in header]
        )
    return out.getvalue()
