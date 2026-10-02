"""Rent index (Mietspiegel) data per municipality (M26-03, decision 8 a of 30.09.2026).

Manual maintenance and CSV import, no automatic source. Each row carries the index name, its
date (Stand), optional criteria (construction year, living area, equipment), the range per m²
and month and a mandatory source note. The lookup returns matching rows with their range and
names the gaps; it does not decide the local comparative rent and states no lawfulness."""

import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.letting.models import RentIndexEntry

router = APIRouter(prefix="/letting/rent-index", tags=["letting"])
READ = require_permission("contracts:read")
WRITE = require_permission("contracts:update")
MAX_CSV_ROWS = 5000
COLUMNS = (
    "gemeinde",
    "name",
    "stand",
    "baujahr_von",
    "baujahr_bis",
    "flaeche_von",
    "flaeche_bis",
    "ausstattung",
    "min",
    "mittel",
    "max",
    "quelle",
)


class RentIndexEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    municipality: str = Field(min_length=2, max_length=120)
    index_name: str = Field(min_length=2, max_length=300)
    valid_from: date
    valid_to: date | None = None
    year_built_from: int | None = Field(default=None, ge=1000, le=2200)
    year_built_to: int | None = Field(default=None, ge=1000, le=2200)
    area_from_sqm: Decimal | None = Field(default=None, ge=0)
    area_to_sqm: Decimal | None = Field(default=None, ge=0)
    equipment: str | None = Field(default=None, max_length=120)
    rent_min: Decimal = Field(gt=0)
    rent_mid: Decimal | None = Field(default=None, gt=0)
    rent_max: Decimal = Field(gt=0)
    source_note: str = Field(min_length=3, max_length=2000)


class RentIndexCsvIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_text: str = Field(min_length=10, max_length=2_000_000)
    dry_run: bool = True


def _out(e: RentIndexEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "municipality": e.municipality,
        "index_name": e.index_name,
        "valid_from": e.valid_from,
        "valid_to": e.valid_to,
        "year_built_from": e.year_built_from,
        "year_built_to": e.year_built_to,
        "area_from_sqm": e.area_from_sqm,
        "area_to_sqm": e.area_to_sqm,
        "equipment": e.equipment,
        "rent_min": e.rent_min,
        "rent_mid": e.rent_mid,
        "rent_max": e.rent_max,
        "source_note": e.source_note,
    }


def _validate(body: RentIndexEntryIn) -> None:
    if body.rent_min > body.rent_max:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Untergrenze über der Obergrenze.")
    if body.rent_mid is not None and not body.rent_min <= body.rent_mid <= body.rent_max:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Mittelwert außerhalb der Spanne.")
    if (
        body.year_built_from is not None
        and body.year_built_to is not None
        and body.year_built_from > body.year_built_to
    ):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Baujahr von nach Baujahr bis.")
    if (
        body.area_from_sqm is not None
        and body.area_to_sqm is not None
        and body.area_from_sqm > body.area_to_sqm
    ):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Fläche von über Fläche bis.")
    if body.valid_to is not None and body.valid_to < body.valid_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gültig bis vor Gültig ab.")


def _number(value: str) -> Decimal | None:
    text = value.strip().replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Zahl ungültig: {value!r}") from None


def _date(value: str) -> date:
    text = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    raise ValueError(f"Datum ungültig: {value!r} (TT.MM.JJJJ)")


def parse_csv(text: str) -> tuple[list[RentIndexEntryIn], list[dict[str, Any]]]:
    """Rows and errors per line. Delimiter semicolon, header with the ``COLUMNS`` names,
    decimal comma and dates as TT.MM.JJJJ accepted."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in ("gemeinde", "name", "stand", "min", "max", "quelle") if c not in header]
    if missing:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Spalten fehlen: " + ", ".join(missing) + "."
        )
    rows: list[RentIndexEntryIn] = []
    errors: list[dict[str, Any]] = []
    for number, raw in enumerate(reader, start=2):
        if number - 1 > MAX_CSV_ROWS:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Höchstens {MAX_CSV_ROWS} Zeilen.")
        r = {k.strip().lower(): (v or "") for k, v in raw.items() if k}
        try:
            entry = RentIndexEntryIn(
                municipality=r["gemeinde"].strip(),
                index_name=r["name"].strip(),
                valid_from=_date(r["stand"]),
                year_built_from=int(r["baujahr_von"]) if r.get("baujahr_von", "").strip() else None,
                year_built_to=int(r["baujahr_bis"]) if r.get("baujahr_bis", "").strip() else None,
                area_from_sqm=_number(r.get("flaeche_von", "")),
                area_to_sqm=_number(r.get("flaeche_bis", "")),
                equipment=r.get("ausstattung", "").strip() or None,
                rent_min=_number(r["min"]),
                rent_mid=_number(r.get("mittel", "")),
                rent_max=_number(r["max"]),
                source_note=r["quelle"].strip(),
            )
            _validate(entry)
        except (ValueError, ProblemError) as exc:
            detail = exc.detail if isinstance(exc, ProblemError) else str(exc)
            errors.append({"line": number, "error": detail})
            continue
        rows.append(entry)
    return rows, errors


@router.get("", summary="Mietspiegelwerte", dependencies=[Depends(strict_query)])
async def list_entries(
    request: Request,
    municipality: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        stmt = select(RentIndexEntry).order_by(
            RentIndexEntry.municipality, RentIndexEntry.valid_from.desc(), RentIndexEntry.rent_min
        )
        if municipality:
            stmt = stmt.where(RentIndexEntry.municipality.ilike(municipality.strip()))
        return [_out(e) for e in (await session.scalars(stmt.limit(2000))).all()]


@router.post("", status_code=201, summary="Mietspiegelwert erfassen")
async def create_entry(
    body: RentIndexEntryIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> dict[str, Any]:
    _validate(body)
    async with tenant_tx(request, principal) as session:
        row = RentIndexEntry(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _out(row)


@router.delete("/{entry_id}", status_code=204, summary="Mietspiegelwert löschen")
async def delete_entry(
    entry_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(RentIndexEntry, entry_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rent_index_entry.deleted",
            entity_type="rent_index_entry",
            entity_id=entry_id,
            actor_user_id=principal.user_id,
            payload={},
        )


@router.post("/import", summary="Mietspiegel per CSV importieren (Vorschau oder Übernahme)")
async def import_csv(
    body: RentIndexCsvIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> dict[str, Any]:
    """Columns (semicolon): gemeinde, name, stand, baujahr_von, baujahr_bis, flaeche_von,
    flaeche_bis, ausstattung, min, mittel, max, quelle. With errors nothing is imported; an
    identical row (municipality, name, Stand, criteria, range) is skipped."""
    rows, errors = parse_csv(body.csv_text)
    created = skipped = 0
    if not body.dry_run:
        if errors:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"{len(errors)} Zeilen fehlerhaft, nichts übernommen (Vorschau prüfen).",
            )
        async with tenant_tx(request, principal) as session:
            for entry in rows:
                same = await session.scalar(
                    select(RentIndexEntry.id).where(
                        RentIndexEntry.municipality == entry.municipality,
                        RentIndexEntry.index_name == entry.index_name,
                        RentIndexEntry.valid_from == entry.valid_from,
                        RentIndexEntry.rent_min == entry.rent_min,
                        RentIndexEntry.rent_max == entry.rent_max,
                        or_(
                            RentIndexEntry.year_built_from == entry.year_built_from,
                            RentIndexEntry.year_built_from.is_(None)
                            & (entry.year_built_from is None),
                        ),
                        or_(
                            RentIndexEntry.area_from_sqm == entry.area_from_sqm,
                            RentIndexEntry.area_from_sqm.is_(None) & (entry.area_from_sqm is None),
                        ),
                        or_(
                            RentIndexEntry.equipment == entry.equipment,
                            RentIndexEntry.equipment.is_(None) & (entry.equipment is None),
                        ),
                    )
                )
                if same is not None:
                    skipped += 1
                    continue
                session.add(
                    RentIndexEntry(
                        tenant_id=principal.tenant_id,
                        created_by=principal.user_id,
                        **entry.model_dump(),
                    )
                )
                created += 1
    return {
        "dry_run": body.dry_run,
        "rows": len(rows),
        "errors": errors,
        "created": created,
        "skipped": skipped,
    }


@router.get("/lookup", summary="Mietspiegelspanne nachschlagen")
async def lookup(
    request: Request,
    municipality: str,
    as_of: date | None = None,
    year_built: int | None = None,
    living_area_sqm: Decimal | None = None,
    equipment: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Matching rows of the newest index valid on the day. A row with a criterion applies only
    when the criterion is given and inside its bounds; rows without a criterion always apply.
    No match is reported as such (no fallback value)."""
    day = as_of or local_today()
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(RentIndexEntry).where(
                    RentIndexEntry.municipality.ilike(municipality.strip()),
                    RentIndexEntry.valid_from <= day,
                    or_(RentIndexEntry.valid_to.is_(None), RentIndexEntry.valid_to >= day),
                )
            )
        ).all()
        if not rows:
            return {"found": False, "matches": [], "notes": ["Kein Mietspiegelwert erfasst."]}
        newest = max((r.valid_from, r.index_name) for r in rows)
        rows = [r for r in rows if (r.valid_from, r.index_name) == newest]
        notes: list[str] = []
        matches: list[RentIndexEntry] = []
        for r in rows:
            if r.year_built_from is not None or r.year_built_to is not None:
                if year_built is None:
                    notes.append("Baujahr fehlt, Zeilen mit Baujahrsklasse nicht prüfbar.")
                    continue
                if (r.year_built_from is not None and year_built < r.year_built_from) or (
                    r.year_built_to is not None and year_built > r.year_built_to
                ):
                    continue
            if r.area_from_sqm is not None or r.area_to_sqm is not None:
                if living_area_sqm is None:
                    notes.append("Wohnfläche fehlt, Zeilen mit Flächenklasse nicht prüfbar.")
                    continue
                if (r.area_from_sqm is not None and living_area_sqm < r.area_from_sqm) or (
                    r.area_to_sqm is not None and living_area_sqm > r.area_to_sqm
                ):
                    continue
            if r.equipment is not None and (
                equipment is None or equipment.strip().lower() != r.equipment.strip().lower()
            ):
                continue
            matches.append(r)
        return {
            "found": bool(matches),
            "index_name": newest[1],
            "index_date": newest[0],
            "matches": [_out(r) for r in matches],
            "notes": sorted(set(notes)),
            "hinweis": (
                "Spanne aus manuell gepflegten Werten. Die Einordnung in die Spanne und die "
                "ortsübliche Vergleichsmiete bleiben eine Entscheidung der Verwaltung."
            ),
        }
