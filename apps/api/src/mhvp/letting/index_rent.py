"""AO03 (GAK-203): index clause and graduated steps of a contract, consumer price index and the
rent increase proposals of the daily job.

Contract fields are inputs only; nothing here changes a rent. The consumer price index is a
platform table maintained by platform administrators via CSV import with source and data date
(no automatic source); only released values feed proposals. Proposals are draft
``rent_increase_case`` rows (switch ``rent_increase_proposals``, default off, question AN18-01).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    require_permission,
    require_platform_admin,
    sessions,
    tenant_tx,
)
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.letting import increase_proposals as ip
from mhvp.workspace.services import local_today

tenant_router = APIRouter(prefix="/letting", tags=["letting"])
platform_router = APIRouter(prefix="/platform/consumer-price-index", tags=["platform"])
READ = require_permission("contracts:read")
UPDATE = require_permission("contracts:update")


class LettingIndexAgreementIo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_name: str = Field(pattern=ip.SERIES_PATTERN)
    base_index: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    base_month: date
    source: str | None = Field(default=None, max_length=500)


class LettingGraduatedStepIo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid_from: date
    net: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class LettingIndexTermsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index_agreement: LettingIndexAgreementIo | None = None
    graduated_steps: list[LettingGraduatedStepIo] = Field(default_factory=list, max_length=60)


class LettingIndexTermsOut(BaseModel):
    contract_id: uuid.UUID
    index_agreement: LettingIndexAgreementIo | None
    graduated_steps: list[LettingGraduatedStepIo]
    latest_index_month: date | None
    latest_index_value: Decimal | None


class LettingProposalOut(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    basis: str
    current_rent: Decimal
    target_rent: Decimal
    effective_date: date
    status: str
    source_note: str | None
    basis_data: dict[str, Any]


class LettingProposalRunOut(BaseModel):
    graduated: int
    index: int
    skipped: int


class LettingCpiOut(BaseModel):
    series: str
    month: date
    value: Decimal
    source: str
    data_as_of: date
    released: bool


class PlatformCpiImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series: str = Field(pattern=ip.SERIES_PATTERN)
    source: str = Field(min_length=3, max_length=500)
    data_as_of: date
    csv: str = Field(min_length=1, max_length=200_000)


class PlatformCpiImportOut(BaseModel):
    created: int
    updated: int
    unchanged: int


class PlatformCpiReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series: str = Field(pattern=ip.SERIES_PATTERN)
    up_to: date


class PlatformCpiReleaseOut(BaseModel):
    released: int


async def _terms(session: Any, contract: Any) -> LettingIndexTermsOut:
    from mhvp.contracts.models import ContractGraduatedStep as Step

    steps = (
        await session.scalars(
            select(Step).where(Step.contract_id == contract.id).order_by(Step.valid_from)
        )
    ).all()
    agreement = contract.index_agreement
    latest = await ip.latest_released_index(session, agreement["index_name"]) if agreement else None
    return LettingIndexTermsOut(
        contract_id=contract.id,
        index_agreement=LettingIndexAgreementIo(**agreement) if agreement else None,
        graduated_steps=[
            LettingGraduatedStepIo(valid_from=s.valid_from, net=s.net, note=s.note) for s in steps
        ],
        latest_index_month=latest[0] if latest else None,
        latest_index_value=latest[1] if latest else None,
    )


async def _tenancy(session: Any, contract_id: uuid.UUID) -> Any:
    from mhvp.contracts.models import Contract, ContractKind

    contract = await session.get(Contract, contract_id)
    if contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if contract.kind is not ContractKind.TENANCY:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Nur für Mietverträge.")
    return contract


@tenant_router.get(
    "/contracts/{contract_id}/index-terms",
    summary="Indexklausel und Staffelstufen des Mietvertrags",
    response_model=LettingIndexTermsOut,
    dependencies=[Depends(strict_query)],
)
async def get_index_terms(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> LettingIndexTermsOut:
    async with tenant_tx(request, principal) as session:
        return await _terms(session, await _tenancy(session, contract_id))


@tenant_router.put(
    "/contracts/{contract_id}/index-terms",
    summary="Indexklausel und Staffelstufen erfassen (nur Eingabe, keine Mietänderung)",
    response_model=LettingIndexTermsOut,
)
async def put_index_terms(
    contract_id: uuid.UUID,
    body: LettingIndexTermsIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> LettingIndexTermsOut:
    from mhvp.accounting.audit_events import record_change
    from mhvp.contracts.models import ContractGraduatedStep as Step

    starts = [s.valid_from for s in body.graduated_steps]
    if len(set(starts)) != len(starts):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Staffelstufe mit gleichem Datum doppelt.")
    if body.index_agreement and body.graduated_steps:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Indexklausel und Staffel schließen sich aus."
        )
    if body.index_agreement and body.index_agreement.base_month.day != 1:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Basismonat ist der Monatserste.")
    async with tenant_tx(request, principal) as session:
        contract = await _tenancy(session, contract_id)
        before = (await _terms(session, contract)).model_dump(mode="json")
        contract.index_agreement = (
            body.index_agreement.model_dump(mode="json") if body.index_agreement else None
        )
        contract.updated_by = principal.user_id
        await session.execute(delete(Step).where(Step.contract_id == contract.id))
        for s in body.graduated_steps:
            session.add(
                Step(
                    tenant_id=principal.tenant_id,
                    contract_id=contract.id,
                    valid_from=s.valid_from,
                    net=s.net,
                    note=s.note,
                    created_by=principal.user_id,
                )
            )
        await session.flush()
        out = await _terms(session, contract)
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            type="contract.updated",
            entity_type="contract",
            entity_id=contract.id,
            before={k: before[k] for k in ("index_agreement", "graduated_steps")},
            after={
                "index_agreement": out.model_dump(mode="json")["index_agreement"],
                "graduated_steps": out.model_dump(mode="json")["graduated_steps"],
            },
        )
        return out


@tenant_router.get(
    "/rent-increase-proposals",
    summary="Vorschläge des Tagesjobs (Staffel, Index), nur Entwürfe",
    response_model=list[LettingProposalOut],
    dependencies=[Depends(strict_query)],
)
async def list_proposals(
    request: Request,
    contract_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[LettingProposalOut]:
    from mhvp.letting.models import RentIncreaseCase as Case

    async with tenant_tx(request, principal) as session:
        query = (
            select(Case)
            .where(Case.status == "draft", Case.check["proposal"].astext == "true")
            .order_by(Case.effective_date, Case.created_at)
        )
        if contract_id is not None:
            query = query.where(Case.contract_id == contract_id)
        rows = (await session.scalars(query.limit(200))).all()
        return [
            LettingProposalOut(
                id=c.id,
                contract_id=c.contract_id,
                basis=c.basis,
                current_rent=c.current_rent,
                target_rent=c.target_rent,
                effective_date=c.effective_date,
                status=c.status,
                source_note=c.source_note,
                basis_data=c.basis_data,
            )
            for c in rows
        ]


@tenant_router.post(
    "/rent-increase-proposals/run",
    summary="Vorschläge jetzt erzeugen (nur mit Schalter Entwurf)",
    response_model=LettingProposalRunOut,
)
async def run_proposals(
    request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> LettingProposalRunOut:
    from mhvp.letting import increase_settings

    async with tenant_tx(request, principal) as session:
        if (await increase_settings.load(session)).proposals != "draft":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Schalter Mieterhöhungsvorschläge ist aus."
            )
        counts = await ip.propose_for_tenant(session, principal.tenant_id, local_today())
    return LettingProposalRunOut(**counts)


@tenant_router.get(
    "/consumer-price-index",
    summary="Verbraucherpreisindex (Plattformdaten, lesend)",
    response_model=list[LettingCpiOut],
    dependencies=[Depends(strict_query)],
)
async def list_cpi(
    request: Request,
    series: str = Query(pattern=ip.SERIES_PATTERN),
    principal: TenantPrincipal = Depends(READ),
) -> list[LettingCpiOut]:
    from mhvp.platform.models import ConsumerPriceIndex as Cpi

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(Cpi).where(Cpi.series == series).order_by(Cpi.month.desc()).limit(200)
            )
        ).all()
        return [
            LettingCpiOut(
                series=r.series,
                month=r.month,
                value=r.value,
                source=r.source,
                data_as_of=r.data_as_of,
                released=r.released,
            )
            for r in rows
        ]


@platform_router.post(
    "/import",
    summary="Indexwerte per CSV importieren (Quelle und Stand Pflicht, nicht freigegeben)",
    response_model=PlatformCpiImportOut,
)
async def import_cpi(
    body: PlatformCpiImportIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> PlatformCpiImportOut:
    """A changed value of a month resets its release; equal values stay as they are."""
    from mhvp.platform.models import ConsumerPriceIndex as Cpi

    try:
        rows = ip.parse_cpi_csv(body.csv)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    created = updated = unchanged = 0
    async with platform_transaction(sessions(request)) as session:
        existing = {
            r.month: r
            for r in (
                await session.scalars(
                    select(Cpi).where(Cpi.series == body.series).with_for_update()
                )
            ).all()
        }
        now = datetime.now(UTC)
        for month, value in rows:
            row = existing.get(month)
            if row is None:
                session.add(
                    Cpi(
                        series=body.series,
                        month=month,
                        value=value,
                        source=body.source,
                        data_as_of=body.data_as_of,
                        imported_by=principal.user_id,
                        imported_at=now,
                    )
                )
                created += 1
            elif row.value != value:
                row.value, row.released = value, False
                row.source, row.data_as_of = body.source, body.data_as_of
                row.imported_by, row.imported_at = principal.user_id, now
                updated += 1
            else:
                unchanged += 1
        await session.flush()
    return PlatformCpiImportOut(created=created, updated=updated, unchanged=unchanged)


@platform_router.post(
    "/release",
    summary="Indexwerte einer Reihe bis Monat freigeben",
    response_model=PlatformCpiReleaseOut,
)
async def release_cpi(
    body: PlatformCpiReleaseIn,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> PlatformCpiReleaseOut:
    from mhvp.platform.models import ConsumerPriceIndex as Cpi

    async with platform_transaction(sessions(request)) as session:
        rows = (
            await session.scalars(
                select(Cpi).where(
                    Cpi.series == body.series, Cpi.month <= body.up_to, Cpi.released.is_(False)
                )
            )
        ).all()
        for r in rows:
            r.released = True
        await session.flush()
    return PlatformCpiReleaseOut(released=len(rows))
