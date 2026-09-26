"""DATEV account mapping endpoints (/api/v1/accounting/datev-mappings, A36, M18-01).

Maintenance (create, change, delete, CSV import) needs ``accounting:update``; the list and the
report of unmapped accounts need ``accounting:read`` (the tax advisor can check but not
maintain). Nothing is preloaded: every row comes from the operator (rule M18-04).
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import datev_mapping as svc
from mhvp.accounting.models import DatevAccountMapping, Ledger
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError

router = APIRouter(prefix="/accounting/datev-mappings", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


class DatevMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID | None
    account_code: str
    datev_account: str
    label: str | None
    active: bool
    valid_from: date | None


class DatevMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID | None = None
    account_code: str = Field(min_length=1, max_length=32)
    datev_account: str = Field(min_length=1, max_length=16, pattern=r"^[0-9]+$")
    label: str | None = Field(default=None, max_length=200)
    active: bool = True
    valid_from: date | None = None


class MappingPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datev_account: str | None = Field(
        default=None, min_length=1, max_length=16, pattern=r"^[0-9]+$"
    )
    label: str | None = Field(default=None, max_length=200)
    active: bool | None = None
    valid_from: date | None = None
    # PATCH cannot express "set to null" for valid_from with the field above; this flag does.
    clear_valid_from: bool = False


class DatevImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2_000_000)
    ledger_id: uuid.UUID | None = None
    # True: preview only (Vorschau), nothing is written.
    dry_run: bool = True


class ImportRowOut(BaseModel):
    line_no: int
    account_code: str | None
    datev_account: str | None
    label: str | None
    valid_from: date | None
    action: Literal["create", "update", "unchanged", "error"]
    error: str | None
    existing_id: uuid.UUID | None
    existing_datev_account: str | None


class DatevImportOut(BaseModel):
    dry_run: bool
    ledger_id: uuid.UUID | None
    rows: list[ImportRowOut]
    file_errors: list[str]
    counts: dict[str, int]


class ReportLineOut(BaseModel):
    account_id: uuid.UUID
    account_code: str
    account_name: str
    datev_account: str | None
    lines_in_period: int
    first_booking_date: date | None
    last_booking_date: date | None
    unmapped: bool
    unmapped_lines: int
    reason: str | None


class ReportOut(BaseModel):
    ledger_id: uuid.UUID
    period_from: date
    period_to: date
    unmapped_count: int
    used_unmapped_count: int
    accounts: list[ReportLineOut]

    @model_validator(mode="after")
    def _period(self) -> "ReportOut":
        if self.period_to < self.period_from:
            raise ValueError("period_to must not lie before period_from")
        return self


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.scalar(select(Ledger).where(Ledger.id == ledger_id))
    if ledger is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            errors=[
                FieldError(
                    location=["body", "ledger_id"],
                    field="ledger_id",
                    code="not_found",
                    message="Buchungskreis nicht gefunden.",
                )
            ],
        )
    return ledger


async def _mapping(session: AsyncSession, mapping_id: uuid.UUID) -> DatevAccountMapping:
    mapping = await session.scalar(
        select(DatevAccountMapping).where(DatevAccountMapping.id == mapping_id)
    )
    if mapping is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return mapping


def _duplicate() -> ProblemError:
    return ProblemError(
        ErrorCodes.CONFLICT,
        detail=(
            "Für dieses Konto, diesen Buchungskreis und dieses Gültig-ab-Datum besteht "
            "bereits eine Zuordnung."
        ),
    )


@router.get("", summary="DATEV-Kontenzuordnungen")
async def list_mappings(
    request: Request,
    ledger_id: uuid.UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    principal: TenantPrincipal = Depends(READ),
) -> list[DatevMappingOut]:
    """With ``ledger_id`` the rows of that ledger plus the tenant wide rows are listed."""
    async with tenant_tx(request, principal) as session:
        query = select(DatevAccountMapping).order_by(
            DatevAccountMapping.account_code,
            DatevAccountMapping.ledger_id.nulls_first(),
            DatevAccountMapping.valid_from.nulls_first(),
        )
        if ledger_id is not None:
            query = query.where(
                (DatevAccountMapping.ledger_id == ledger_id)
                | (DatevAccountMapping.ledger_id.is_(None))
            )
        if not include_inactive:
            query = query.where(DatevAccountMapping.active.is_(True))
        return [DatevMappingOut.model_validate(m) for m in (await session.scalars(query)).all()]


@router.post("", status_code=201, summary="DATEV-Kontenzuordnung anlegen")
async def create_mapping(
    body: DatevMappingIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> DatevMappingOut:
    async with tenant_tx(request, principal) as session:
        if body.ledger_id is not None:
            await _ledger(session, body.ledger_id)
        mapping = DatevAccountMapping(
            tenant_id=principal.tenant_id,
            ledger_id=body.ledger_id,
            account_code=body.account_code.strip(),
            datev_account=body.datev_account,
            label=body.label,
            active=body.active,
            valid_from=body.valid_from,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(mapping)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise _duplicate() from exc
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="datev_mapping.created",
            entity_type="datev_account_mapping",
            entity_id=mapping.id,
            actor_user_id=principal.user_id,
            payload={"account_code": mapping.account_code, "datev_account": mapping.datev_account},
        )
        return DatevMappingOut.model_validate(mapping)


@router.patch("/{mapping_id}", summary="DATEV-Kontenzuordnung ändern")
async def update_mapping(
    mapping_id: uuid.UUID,
    body: MappingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> DatevMappingOut:
    async with tenant_tx(request, principal) as session:
        mapping = await _mapping(session, mapping_id)
        data = body.model_dump(exclude_unset=True, exclude={"clear_valid_from"})
        for key, value in data.items():
            setattr(mapping, key, value)
        if body.clear_valid_from:
            mapping.valid_from = None
        mapping.updated_by = principal.user_id
        try:
            await session.flush()
        except IntegrityError as exc:
            raise _duplicate() from exc
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="datev_mapping.updated",
            entity_type="datev_account_mapping",
            entity_id=mapping.id,
            actor_user_id=principal.user_id,
            payload={"changes": sorted(data)},
        )
        return DatevMappingOut.model_validate(mapping)


@router.delete("/{mapping_id}", status_code=204, summary="DATEV-Kontenzuordnung löschen")
async def delete_mapping(
    mapping_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> None:
    """Master data only; exports already written keep their content and checksum."""
    async with tenant_tx(request, principal) as session:
        mapping = await _mapping(session, mapping_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="datev_mapping.deleted",
            entity_type="datev_account_mapping",
            entity_id=mapping.id,
            actor_user_id=principal.user_id,
            payload={"account_code": mapping.account_code, "datev_account": mapping.datev_account},
        )
        await session.delete(mapping)
        await session.flush()


@router.post("/import", summary="Zuordnungen aus CSV (Vorschau oder Übernahme)")
async def import_mappings(
    body: DatevImportIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> DatevImportOut:
    """CSV with header ``account_code;datev_account;label;valid_from`` (German aliases
    accepted, semicolon or comma). ``dry_run=true`` returns the preview only. A file with any
    row error is not written at all (``dry_run=false`` then answers 422 with the rows)."""
    async with tenant_tx(request, principal) as session:
        if body.ledger_id is not None:
            await _ledger(session, body.ledger_id)
        rows, file_errors = await svc.plan_import(
            session, tenant_id=principal.tenant_id, ledger_id=body.ledger_id, content=body.content
        )
        counts = {
            "create": sum(1 for r in rows if r.action == "create"),
            "update": sum(1 for r in rows if r.action == "update"),
            "unchanged": sum(1 for r in rows if r.action == "unchanged"),
            "error": sum(1 for r in rows if r.action == "error"),
        }
        rows_out = [ImportRowOut(**svc.row_to_dict(r)) for r in rows]
        if body.dry_run:
            return DatevImportOut(
                dry_run=True,
                ledger_id=body.ledger_id,
                rows=rows_out,
                file_errors=file_errors,
                counts=counts,
            )
        if file_errors or counts["error"]:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Datei enthält fehlerhafte Zeilen; nichts wurde übernommen.",
                extensions={
                    "file_errors": file_errors,
                    "rows": [r.model_dump(mode="json") for r in rows_out if r.action == "error"],
                },
            )
        written = await svc.apply_import(
            session,
            rows,
            tenant_id=principal.tenant_id,
            ledger_id=body.ledger_id,
            actor_user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="datev_mapping.imported",
            entity_type="ledger" if body.ledger_id else "tenant",
            entity_id=body.ledger_id or principal.tenant_id,
            actor_user_id=principal.user_id,
            payload=written,
        )
        return DatevImportOut(
            dry_run=False,
            ledger_id=body.ledger_id,
            rows=rows_out,
            file_errors=[],
            counts={**counts, **written},
        )


@router.get("/report", summary="Prüfbericht nicht zugeordnete Konten")
async def mapping_report(
    request: Request,
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    principal: TenantPrincipal = Depends(READ),
) -> ReportOut:
    """Per ledger and period: every account of the ledger with its resolved DATEV account,
    posted lines in the period and whether a line or the account as of the period end lacks
    a mapping. The same check blocks the batch export (MHVP-BILL-0008)."""
    if end < start:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            errors=[
                FieldError(
                    location=["query", "end"],
                    field="end",
                    code="range",
                    message="end darf nicht vor start liegen.",
                )
            ],
        )
    async with tenant_tx(request, principal) as session:
        ledger = await session.scalar(select(Ledger).where(Ledger.id == ledger_id))
        if ledger is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        # A37: a scoped membership (tax advisor) sees only its assigned legal entities.
        ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
        result = await svc.report(session, ledger, start, end)
        return ReportOut(
            ledger_id=result.ledger_id,
            period_from=result.period_from,
            period_to=result.period_to,
            unmapped_count=result.unmapped_count,
            used_unmapped_count=result.used_unmapped_count,
            accounts=[ReportLineOut(**a.__dict__) for a in result.accounts],
        )
