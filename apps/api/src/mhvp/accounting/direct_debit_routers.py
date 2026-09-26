"""Direct debit endpoints (/api/v1/accounting/direct-debits, M15, 7.5 SEPA, rule M15-02).

Rights as for payment runs: ``accounting:read`` to look, ``accounting:create`` to prepare,
``accounting:approve`` for the four eyes approval and the file. The file is generated and
filed as a document without any gate; handing it out (download) requires release gate G2,
which stays closed by default. Nothing here transmits anything to a bank.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import insert, select, update

from mhvp.accounting import direct_debit as dd
from mhvp.accounting.direct_debit_models import DirectDebitRun, DirectDebitRunStatus
from mhvp.accounting.models import Ledger
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.ids import uuid7
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents.blobs import BlobStore
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting/direct-debits", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreviewIn(_In):
    ledger_id: uuid.UUID
    collection_date: date
    lead_days: int = Field(ge=0, le=60)


class DirectDebitRunIn(PreviewIn):
    property_bank_account_id: uuid.UUID
    open_item_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=2000)


class CreditorIdIn(_In):
    sepa_creditor_id: str | None = Field(default=None, min_length=1, max_length=35)


class DirectDebitOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    open_item_id: uuid.UUID
    contract_id: uuid.UUID | None
    contact_id: uuid.UUID
    contact_bank_account_id: uuid.UUID
    mandate_reference: str
    mandate_signed_on: date
    mandate_scheme: str
    sequence_type: str
    amount: Decimal
    debtor_name: str
    debtor_iban_suffix: str | None = None
    purpose: str
    end_to_end_id: str
    due_date: date
    pre_notification_document_id: uuid.UUID | None
    pre_notification_dispatch_id: uuid.UUID | None


class DirectDebitRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID
    legal_entity_id: uuid.UUID
    property_bank_account_id: uuid.UUID
    creditor_id: str
    creditor_name: str
    collection_date: date
    lead_days: int
    message_id: str
    format: str
    status: str
    control_sum: Decimal
    transaction_count: int
    document_id: uuid.UUID | None
    excluded: list[dict[str, Any]]
    exported_at: datetime | None
    approvals: int = 0
    orders: list[DirectDebitOrderOut] = Field(default_factory=list)


async def _run_out(session: Any, run: DirectDebitRun) -> DirectDebitRunOut:
    return (await _runs_out(session, [run]))[0]


async def _runs_out(session: Any, runs: Sequence[DirectDebitRun]) -> list[DirectDebitRunOut]:
    """Orders and valid approvals of all runs in two queries (performance review 26.09.2026)."""
    if not runs:
        return []
    orders = await dd.orders_of_runs(session, [r.id for r in runs])
    approvals = await dd.valid_approvals_of_runs(session, runs, orders)
    out = []
    for run in runs:
        row = DirectDebitRunOut.model_validate(run)
        row.approvals = len({a.user_id for a in approvals.get(run.id, [])})
        row.orders = []
        for o in orders.get(run.id, []):
            item = DirectDebitOrderOut.model_validate(o)
            item.debtor_iban_suffix = o.debtor_iban[-4:]
            row.orders.append(item)
        out.append(row)
    return out


async def _run(session: Any, run_id: uuid.UUID) -> DirectDebitRun:
    run = await session.get(DirectDebitRun, run_id, with_for_update=True)
    if run is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return run  # type: ignore[no-any-return]


async def _ledger(session: Any, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    return ledger  # type: ignore[no-any-return]


@router.put(
    "/creditor-ids/legal-entities/{legal_entity_id}",
    summary="Gläubiger-Identifikationsnummer des Rechtsträgers hinterlegen",
)
async def set_creditor_id(
    legal_entity_id: uuid.UUID,
    body: CreditorIdIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.properties.models import LegalEntity

    async with tenant_tx(request, principal) as session:
        entity = await session.get(LegalEntity, legal_entity_id)
        if entity is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        entity.sepa_creditor_id = body.sepa_creditor_id
        entity.updated_by = principal.user_id
        await session.flush()
        return {"legal_entity_id": entity.id, "sepa_creditor_id": entity.sepa_creditor_id}


@router.put(
    "/creditor-ids/tenant", summary="Gläubiger-Identifikationsnummer des Mandanten (Rückfall)"
)
async def set_tenant_creditor_id(
    body: CreditorIdIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> dict[str, Any]:
    from mhvp.platform.models import TenantBillingSettings

    async with tenant_tx(request, principal) as session:
        existing = await session.scalar(select(TenantBillingSettings.id).limit(1))
        if existing is None:
            await session.execute(
                insert(TenantBillingSettings).values(
                    id=uuid7(),
                    tenant_id=principal.tenant_id,
                    sepa_creditor_id=body.sepa_creditor_id,
                )
            )
        else:
            await session.execute(
                update(TenantBillingSettings)
                .where(TenantBillingSettings.id == existing)
                .values(sepa_creditor_id=body.sepa_creditor_id)
            )
        return {"tenant_id": principal.tenant_id, "sepa_creditor_id": body.sepa_creditor_id}


@router.post("/preview", summary="Einziehbare Sollstellungen (Vorschau)")
async def preview(
    body: PreviewIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        dd.check_lead_time(body.collection_date, body.lead_days, local_today())
        selection = await dd.select_due(
            session, ledger=ledger, collection_date=body.collection_date
        )
        eligible = selection.eligible
        return {
            "ledger_id": ledger.id,
            "legal_entity_id": selection.legal_entity_id,
            "creditor_id": selection.creditor_id,
            "collection_date": body.collection_date,
            "count": len(eligible),
            "control_sum": str(sum((c.amount for c in eligible), Decimal("0.00"))),
            "items": [c.as_dict() for c in selection.candidates],
        }


@router.get("", summary="Lastschriftläufe")
async def list_runs(
    request: Request,
    status: str | None = Query(
        default=None, pattern="^(" + "|".join(s.value for s in DirectDebitRunStatus) + ")$"
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> list[DirectDebitRunOut]:
    async with tenant_tx(request, principal) as session:
        query = select(DirectDebitRun).order_by(
            DirectDebitRun.collection_date.desc(), DirectDebitRun.id
        )
        if status is not None:
            query = query.where(DirectDebitRun.status == DirectDebitRunStatus(status))
        rows = (await session.scalars(query.limit(limit))).all()
        return await _runs_out(session, rows)


@router.post("", status_code=201, summary="Lastschriftlauf anlegen (Entwurf)")
async def create_run(
    body: DirectDebitRunIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> DirectDebitRunOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        run = await dd.create_run(
            session,
            ledger=ledger,
            bank_account_id=body.property_bank_account_id,
            collection_date=body.collection_date,
            lead_days=body.lead_days,
            today=local_today(),
            open_item_ids=body.open_item_ids,
            user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="direct_debit_run.created",
            entity_type="direct_debit_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"orders": run.transaction_count, "control_sum": str(run.control_sum)},
        )
        return await _run_out(session, run)


@router.get("/{run_id}", summary="Lastschriftlauf")
async def get_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> DirectDebitRunOut:
    async with tenant_tx(request, principal) as session:
        run = await session.get(DirectDebitRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _run_out(session, run)


@router.post("/{run_id}/approve", summary="Freigabe (zwei verschiedene Personen)")
async def approve_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> DirectDebitRunOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Approvals need a person.")
    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        await dd.approve(session, run, principal.user_id, principal.is_platform_admin)
        return await _run_out(session, run)


@router.post("/{run_id}/cancel", summary="Lauf verwerfen")
async def cancel_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> DirectDebitRunOut:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        if run.status is DirectDebitRunStatus.EXPORTED:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Ausgegebene Dateien werden über die Bank storniert."
            )
        run.status = DirectDebitRunStatus.CANCELLED
        run.updated_by = principal.user_id
        await dd.invalidate(session, run)
        return await _run_out(session, run)


@router.post("/{run_id}/file", summary="Lastschriftdatei erzeugen und ablegen (nicht übermittelt)")
async def generate_file(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> DirectDebitRunOut:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        _, document_id = await dd.generate_file(
            session, BlobStore(request.app.state.settings), run, user_id=principal.user_id
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="direct_debit_run.file_generated",
            entity_type="direct_debit_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"document_id": str(document_id), "format": run.format},
        )
        return await _run_out(session, run)


@router.get("/{run_id}/file", summary="Lastschriftdatei herunterladen (G2)")
async def download_file(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    await ensure_release_gate_open(
        ReleaseGate.G2, principal.tenant_id, request.app.state.release_gate_resolver
    )
    from mhvp.documents.models import Document

    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        if run.status not in (DirectDebitRunStatus.FILE_GENERATED, DirectDebitRunStatus.EXPORTED):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Für den Lauf liegt keine Datei vor.")
        document = await session.get(Document, run.document_id) if run.document_id else None
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Datei nicht gefunden.")
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        if run.status is not DirectDebitRunStatus.EXPORTED:
            run.status = DirectDebitRunStatus.EXPORTED
            run.exported_at, run.exported_by = datetime.now(UTC), principal.user_id
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="direct_debit_run.exported",
                entity_type="direct_debit_run",
                entity_id=run.id,
                actor_user_id=principal.user_id,
                payload={"document_id": str(document.id)},
            )
        await session.flush()
        return Response(
            content=data,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
        )


@router.post("/{run_id}/pre-notifications", summary="Vorabinformationen je Zahler (Entwurf)")
async def pre_notifications(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, run_id)
        return await dd.create_pre_notifications(
            session, BlobStore(request.app.state.settings), run, principal=principal
        )


@router.get("/{run_id}/orders", summary="Lastschriften eines Laufs")
async def list_orders(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[DirectDebitOrderOut]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(DirectDebitRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return (await _run_out(session, run)).orders
