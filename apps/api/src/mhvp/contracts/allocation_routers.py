"""Allocation agreements per tenancy and cost position (M17-01, AE17).

Records the clause reference, proof document and validity under which a BetrKV catalogue
position is passed on to a tenancy. Bulk entry per property previews first (``dry_run`` is the
default) and never overwrites an existing agreement. The report of missing bases lives in
``mhvp.billing.allocation_basis``.
"""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.billing import betrkv
from mhvp.billing.models import Statement
from mhvp.billing.status import StatementStatus
from mhvp.contracts.models import AllocationAgreement, Contract, ContractKind
from mhvp.contracts.routers import CREATE, READ, UPDATE, _event, _get
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.properties.models import Property

router = APIRouter(tags=["Verträge"])


class AllocationAgreementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operating_cost_type: str = Field(min_length=1, max_length=40)
    status: str = Field(default="agreed", pattern="^(agreed|excluded)$")
    clause_reference: str | None = Field(default=None, max_length=2000)
    document_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _check(self) -> "AllocationAgreementIn":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        if self.status == "agreed" and not (self.clause_reference or "").strip():
            raise ValueError("Klauselbezug fehlt")
        return self


class AllocationAgreementPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = Field(default=None, pattern="^(agreed|excluded)$")
    clause_reference: str | None = Field(default=None, max_length=2000)
    document_id: uuid.UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    note: str | None = Field(default=None, max_length=4000)


class AllocationAgreementBulkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operating_cost_type: str = Field(min_length=1, max_length=40)
    status: str = Field(default="agreed", pattern="^(agreed|excluded)$")
    clause_reference: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check(self) -> "AllocationAgreementBulkItem":
        if self.status == "agreed" and not (self.clause_reference or "").strip():
            raise ValueError("Klauselbezug fehlt")
        return self


class AllocationAgreementBulkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AllocationAgreementBulkItem] = Field(min_length=1, max_length=40)
    document_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    dry_run: bool = True

    @model_validator(mode="after")
    def _check(self) -> "AllocationAgreementBulkIn":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self


def _out(a: AllocationAgreement) -> dict[str, Any]:
    entry = betrkv.get(a.operating_cost_type)
    return {
        "id": a.id,
        "contract_id": a.contract_id,
        "operating_cost_type": a.operating_cost_type,
        "operating_cost_label": entry.label if entry else None,
        "status": a.status,
        "clause_reference": a.clause_reference,
        "document_id": a.document_id,
        "valid_from": a.valid_from,
        "valid_to": a.valid_to,
        "note": a.note,
    }


def _check_type(code: str) -> None:
    if betrkv.get(code) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannte Katalogposition {code}.")


async def _check_document(session: Any, document_id: uuid.UUID | None) -> None:
    if document_id is not None and await session.get(Document, document_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument nicht gefunden.")


async def _overlap(
    session: Any,
    contract_id: uuid.UUID,
    code: str,
    start: date,
    end: date | None,
    skip: uuid.UUID | None = None,
) -> bool:
    query = select(AllocationAgreement.id).where(
        AllocationAgreement.contract_id == contract_id,
        AllocationAgreement.operating_cost_type == code,
        or_(AllocationAgreement.valid_to.is_(None), AllocationAgreement.valid_to >= start),
    )
    if end is not None:
        query = query.where(AllocationAgreement.valid_from <= end)
    if skip is not None:
        query = query.where(AllocationAgreement.id != skip)
    return (await session.scalar(query.limit(1))) is not None


async def _tenancy(session: Any, contract_id: uuid.UUID, *, lock: bool = False) -> Contract:
    contract: Contract = await _get(session, Contract, contract_id, lock=lock)
    if contract.kind is not ContractKind.TENANCY:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Umlagevereinbarungen gelten für Mietverträge."
        )
    return contract


@router.get(
    "/contracts/{contract_id}/allocation-agreements",
    summary="Umlagevereinbarungen eines Mietvertrags",
    dependencies=[Depends(strict_query)],
)
async def list_agreements(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(AllocationAgreement)
                .where(AllocationAgreement.contract_id == contract_id)
                .order_by(AllocationAgreement.operating_cost_type, AllocationAgreement.valid_from)
            )
        ).all()
        return {"items": [_out(r) for r in rows]}


@router.post(
    "/contracts/{contract_id}/allocation-agreements",
    status_code=201,
    summary="Umlagevereinbarung erfassen",
)
async def create_agreement(
    contract_id: uuid.UUID,
    body: AllocationAgreementIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _tenancy(session, contract_id)
        _check_type(body.operating_cost_type)
        await _check_document(session, body.document_id)
        if await _overlap(
            session, contract_id, body.operating_cost_type, body.valid_from, body.valid_to
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Für diesen Zeitraum besteht bereits eine Vereinbarung."
            )
        row = AllocationAgreement(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            contract_id=contract_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        await _event(session, principal, "allocation_agreement.created", row.id)
        return _out(row)


@router.patch(
    "/contracts/{contract_id}/allocation-agreements/{agreement_id}",
    summary="Umlagevereinbarung ändern",
)
async def patch_agreement(
    contract_id: uuid.UUID,
    agreement_id: uuid.UUID,
    body: AllocationAgreementPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _tenancy(session, contract_id)
        row = await session.get(AllocationAgreement, agreement_id, with_for_update=True)
        if row is None or row.contract_id != contract_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        merged = {**_out(row), **data}
        if merged["valid_to"] is not None and merged["valid_to"] < merged["valid_from"]:
            raise ProblemError(ErrorCodes.VALIDATION, detail="valid_to liegt vor valid_from.")
        if merged["status"] == "agreed" and not (merged["clause_reference"] or "").strip():
            raise ProblemError(ErrorCodes.VALIDATION, detail="Klauselbezug fehlt.")
        await _check_document(session, data.get("document_id"))
        if await _overlap(
            session,
            contract_id,
            row.operating_cost_type,
            merged["valid_from"],
            merged["valid_to"],
            skip=row.id,
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Für diesen Zeitraum besteht bereits eine Vereinbarung."
            )
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Konflikt beim Speichern.") from None
        await _event(session, principal, "allocation_agreement.updated", row.id)
        return _out(row)


@router.delete(
    "/contracts/{contract_id}/allocation-agreements/{agreement_id}",
    status_code=204,
    summary="Umlagevereinbarung löschen (nicht nach begonnener Abrechnung)",
)
async def delete_agreement(
    contract_id: uuid.UUID,
    agreement_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        contract = await _tenancy(session, contract_id)
        row = await session.get(AllocationAgreement, agreement_id, with_for_update=True)
        if row is None or row.contract_id != contract_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        used = await session.scalar(
            select(Statement.id)
            .where(
                Statement.property_id == contract.property_id,
                Statement.status != StatementStatus.DRAFT,
                Statement.period_from <= (row.valid_to or date.max),
                Statement.period_to >= row.valid_from,
            )
            .limit(1)
        )
        if used is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Eine Abrechnung nutzt den Zeitraum bereits, bitte per valid_to beenden.",
            )
        await _event(session, principal, "allocation_agreement.deleted", row.id)
        await session.delete(row)


@router.post(
    "/properties/{property_id}/allocation-agreements/bulk",
    summary="Massenerfassung der Umlagevereinbarungen für alle Mietverträge eines Objekts",
)
async def bulk_agreements(
    property_id: uuid.UUID,
    body: AllocationAgreementBulkIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.core.auth.scope import ensure_session_property_allowed

    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ensure_session_property_allowed(session, property_id)
        for item in body.items:
            _check_type(item.operating_cost_type)
        await _check_document(session, body.document_id)
        contracts = (
            await session.scalars(
                select(Contract)
                .where(
                    Contract.property_id == property_id,
                    Contract.kind == ContractKind.TENANCY,
                    or_(Contract.end_date.is_(None), Contract.end_date >= body.valid_from),
                )
                .order_by(Contract.number)
            )
        ).all()
        created = skipped = 0
        skipped_rows: list[dict[str, Any]] = []
        for contract in contracts:
            for item in body.items:
                if await _overlap(
                    session, contract.id, item.operating_cost_type, body.valid_from, body.valid_to
                ):
                    skipped += 1
                    skipped_rows.append(
                        {
                            "contract_id": contract.id,
                            "operating_cost_type": item.operating_cost_type,
                        }
                    )
                    continue
                created += 1
                if not body.dry_run:
                    session.add(
                        AllocationAgreement(
                            tenant_id=principal.tenant_id,
                            created_by=principal.user_id,
                            contract_id=contract.id,
                            operating_cost_type=item.operating_cost_type,
                            status=item.status,
                            clause_reference=item.clause_reference,
                            document_id=body.document_id,
                            valid_from=body.valid_from,
                            valid_to=body.valid_to,
                        )
                    )
        if not body.dry_run:
            await session.flush()
            await _event(
                session, principal, "allocation_agreement.bulk", property_id, created=created
            )
        return {
            "dry_run": body.dry_run,
            "contracts": len(contracts),
            "created": created,
            "skipped": skipped,
            "skipped_rows": skipped_rows,
        }
