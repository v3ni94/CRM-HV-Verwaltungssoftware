"""Settings page "Einstellungen, Schnittstellen" for lexoffice (M13-lexoffice): connection
config, connection test, run protocol, explicit export (invoices, contacts) and explicit
import (receipts). Nothing here runs on a schedule or automatically; every export and import
is one logged, operator triggered call (rule 0.1.1, 0.1.4, 0.1.6).

Export needs release gate G1 (productive bookkeeping) open for the tenant in addition to the
``LexofficeTenantConfig.enabled`` flag; both default closed (ADR 0003). Import only creates a
``ReceiptDraft`` (never a posting), so it needs the feature flag but not G1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice
from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, require_release_gate
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentSource
from mhvp.documents.services import store_document
from mhvp.integrations import schemas as s
from mhvp.integrations.lexoffice import LexofficeClient, LexofficeCredentials
from mhvp.integrations.models import (
    LexofficeExportKind,
    LexofficeExportLink,
    LexofficeRunKind,
    LexofficeRunStatus,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)
from mhvp.receipts.models import ReceiptDraft, ReceiptDraftSource, ReceiptDraftStatus

router = APIRouter(prefix="/integrations/lexoffice", tags=["Schnittstellen"])

SETTINGS = require_permission("tenant_settings:update")
EXPORT = require_permission("accounting:create")
IMPORT = require_permission("accounting:create")
READ = require_permission("accounting:read")
G1 = require_release_gate(ReleaseGate.G1)


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


async def _config(session: AsyncSession, tenant_id: uuid.UUID) -> LexofficeTenantConfig | None:
    result: LexofficeTenantConfig | None = await session.scalar(
        select(LexofficeTenantConfig).where(LexofficeTenantConfig.tenant_id == tenant_id)
    )
    return result


def _client_for(config: LexofficeTenantConfig) -> LexofficeClient:
    if not config.enabled or not config.api_key:
        raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
    return LexofficeClient(LexofficeCredentials(api_key=config.api_key, base_url=config.base_url))


async def _run(
    session: AsyncSession, principal: TenantPrincipal, kind: LexofficeRunKind
) -> LexofficeSyncRun:
    run = LexofficeSyncRun(
        tenant_id=principal.tenant_id,
        kind=kind.value,
        status=LexofficeRunStatus.RUNNING.value,
        started_by=principal.user_id,
    )
    session.add(run)
    await session.flush()
    return run


async def _finish_run(
    session: AsyncSession, run: LexofficeSyncRun, counts: dict[str, int], errors: list[str]
) -> None:
    run.counts = counts
    run.errors = errors
    if not errors:
        run.status = LexofficeRunStatus.OK.value
    elif counts.get("ok", 0):
        run.status = LexofficeRunStatus.PARTIAL.value
    else:
        run.status = LexofficeRunStatus.FAILED.value
    run.finished_at = datetime.now(UTC)
    await session.flush()


@router.get("/config", summary="lexoffice-Anbindung lesen")
async def get_config(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.LexofficeConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        if config is None:
            return s.LexofficeConfigOut(
                tenant_id=principal.tenant_id,
                base_url="https://api.lexware.io",
                enabled=False,
                api_key_set=False,
                last_tested_at=None,
                last_test_ok=None,
                last_test_message=None,
            )
        return s.LexofficeConfigOut(
            tenant_id=config.tenant_id,
            base_url=config.base_url,
            enabled=config.enabled,
            api_key_set=bool(config.api_key),
            last_tested_at=config.last_tested_at,
            last_test_ok=config.last_test_ok,
            last_test_message=config.last_test_message,
        )


@router.put("/config", summary="lexoffice-Anbindung einrichten")
async def put_config(
    body: s.LexofficeConfigIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.LexofficeConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        if config is None:
            config = LexofficeTenantConfig(tenant_id=principal.tenant_id)
            session.add(config)
        if body.base_url:
            config.base_url = body.base_url
        if body.api_key is not None:
            config.api_key = body.api_key
        config.enabled = body.enabled
        if config.enabled and not config.api_key:
            raise _invalid("Ohne API-Schlüssel kann die Anbindung nicht aktiviert werden.")
        await session.flush()
        return s.LexofficeConfigOut(
            tenant_id=config.tenant_id,
            base_url=config.base_url,
            enabled=config.enabled,
            api_key_set=bool(config.api_key),
            last_tested_at=config.last_tested_at,
            last_test_ok=config.last_test_ok,
            last_test_message=config.last_test_message,
        )


@router.post("/test", summary="Verbindung testen")
async def check_connection(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.LexofficeConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        if config is None or not config.api_key:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        run = await _run(session, principal, LexofficeRunKind.TEST)
        client = LexofficeClient(
            LexofficeCredentials(api_key=config.api_key, base_url=config.base_url)
        )
        try:
            client.test_connection()
        except ProblemError as exc:
            config.last_tested_at = datetime.now(UTC)
            config.last_test_ok = False
            config.last_test_message = exc.detail
            await _finish_run(session, run, {"ok": 0, "failed": 1}, [str(exc.detail)])
        else:
            config.last_tested_at = datetime.now(UTC)
            config.last_test_ok = True
            config.last_test_message = "Verbindung erfolgreich."
            await _finish_run(session, run, {"ok": 1, "failed": 0}, [])
        await session.flush()
        return s.LexofficeConfigOut(
            tenant_id=config.tenant_id,
            base_url=config.base_url,
            enabled=config.enabled,
            api_key_set=bool(config.api_key),
            last_tested_at=config.last_tested_at,
            last_test_ok=config.last_test_ok,
            last_test_message=config.last_test_message,
        )


@router.get("/runs", summary="Letzte Läufe")
async def list_runs(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.LexofficeRunOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(LexofficeSyncRun)
                .where(LexofficeSyncRun.tenant_id == principal.tenant_id)
                .order_by(LexofficeSyncRun.created_at.desc())
                .limit(50)
            )
        ).all()
        return [s.LexofficeRunOut.model_validate(r) for r in rows]


async def _already_exported(
    session: AsyncSession, tenant_id: uuid.UUID, kind: LexofficeExportKind, entity_id: uuid.UUID
) -> LexofficeExportLink | None:
    result: LexofficeExportLink | None = await session.scalar(
        select(LexofficeExportLink).where(
            LexofficeExportLink.tenant_id == tenant_id,
            LexofficeExportLink.entity_kind == kind.value,
            LexofficeExportLink.entity_id == entity_id,
        )
    )
    return result


@router.post(
    "/export/invoices",
    summary="Ausgangsrechnungen/Belege nach lexoffice exportieren",
    dependencies=[Depends(G1)],
)
async def export_invoices(
    body: s.LexofficeExportInvoicesIn,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> s.LexofficeExportResult:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        client = _client_for(config) if config else None
        if client is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        run = await _run(session, principal, LexofficeRunKind.EXPORT_INVOICES)
        results: list[s.LexofficeExportResultItem] = []
        ok = failed = 0
        errors: list[str] = []
        for item in body.items:
            invoice = await session.get(Invoice, item.invoice_id)
            if invoice is None or invoice.tenant_id != principal.tenant_id:
                failed += 1
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.invoice_id, ok=False, error="Rechnung nicht gefunden."
                    )
                )
                continue
            existing = await _already_exported(
                session, principal.tenant_id, LexofficeExportKind.INVOICE, item.invoice_id
            )
            if existing is not None and not item.force:
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.invoice_id,
                        ok=True,
                        lexoffice_id=existing.lexoffice_id,
                        skipped_duplicate=True,
                    )
                )
                continue
            try:
                created = client.create_voucher(item.payload)
                lexoffice_id = str(created.get("id") or created.get("voucherId") or "")
                if not lexoffice_id:
                    raise ProblemError(
                        ErrorCodes.LEXOFFICE_UNAVAILABLE,
                        detail="lexoffice-Antwort enthielt keine ID.",
                    )
            except ProblemError as exc:
                failed += 1
                errors.append(f"invoice {item.invoice_id}: {exc.detail}")
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.invoice_id, ok=False, error=str(exc.detail)
                    )
                )
                continue
            if existing is not None:
                existing.lexoffice_id = lexoffice_id
                existing.run_id = run.id
            else:
                session.add(
                    LexofficeExportLink(
                        tenant_id=principal.tenant_id,
                        entity_kind=LexofficeExportKind.INVOICE.value,
                        entity_id=item.invoice_id,
                        lexoffice_id=lexoffice_id,
                        run_id=run.id,
                    )
                )
            ok += 1
            results.append(
                s.LexofficeExportResultItem(
                    entity_id=item.invoice_id, ok=True, lexoffice_id=lexoffice_id
                )
            )
        await _finish_run(session, run, {"ok": ok, "failed": failed}, errors)
        return s.LexofficeExportResult(run_id=run.id, items=results)


@router.post(
    "/export/contacts",
    summary="Kontakte nach lexoffice exportieren",
    dependencies=[Depends(G1)],
)
async def export_contacts(
    body: s.LexofficeExportContactsIn,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> s.LexofficeExportResult:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        client = _client_for(config) if config else None
        if client is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        run = await _run(session, principal, LexofficeRunKind.EXPORT_CONTACTS)
        results: list[s.LexofficeExportResultItem] = []
        ok = failed = 0
        errors: list[str] = []
        for item in body.items:
            contact = await session.get(Contact, item.contact_id)
            if contact is None or contact.tenant_id != principal.tenant_id:
                failed += 1
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.contact_id, ok=False, error="Kontakt nicht gefunden."
                    )
                )
                continue
            existing = await _already_exported(
                session, principal.tenant_id, LexofficeExportKind.CONTACT, item.contact_id
            )
            if existing is not None and not item.force:
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.contact_id,
                        ok=True,
                        lexoffice_id=existing.lexoffice_id,
                        skipped_duplicate=True,
                    )
                )
                continue
            try:
                created = client.create_contact(item.payload)
                lexoffice_id = str(created.get("id") or "")
                if not lexoffice_id:
                    raise ProblemError(
                        ErrorCodes.LEXOFFICE_UNAVAILABLE,
                        detail="lexoffice-Antwort enthielt keine ID.",
                    )
            except ProblemError as exc:
                failed += 1
                errors.append(f"contact {item.contact_id}: {exc.detail}")
                results.append(
                    s.LexofficeExportResultItem(
                        entity_id=item.contact_id, ok=False, error=str(exc.detail)
                    )
                )
                continue
            if existing is not None:
                existing.lexoffice_id = lexoffice_id
                existing.run_id = run.id
            else:
                session.add(
                    LexofficeExportLink(
                        tenant_id=principal.tenant_id,
                        entity_kind=LexofficeExportKind.CONTACT.value,
                        entity_id=item.contact_id,
                        lexoffice_id=lexoffice_id,
                        run_id=run.id,
                    )
                )
            ok += 1
            results.append(
                s.LexofficeExportResultItem(
                    entity_id=item.contact_id, ok=True, lexoffice_id=lexoffice_id
                )
            )
        await _finish_run(session, run, {"ok": ok, "failed": failed}, errors)
        return s.LexofficeExportResult(run_id=run.id, items=results)


@router.post("/import/receipts", summary="Belege aus lexoffice als Belegentwurf importieren")
async def import_receipts(
    body: s.LexofficeImportReceiptsIn,
    request: Request,
    principal: TenantPrincipal = Depends(IMPORT),
) -> s.LexofficeImportResult:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        client = _client_for(config) if config else None
        if client is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        blobs = BlobStore(request.app.state.settings)
        run = await _run(session, principal, LexofficeRunKind.IMPORT_RECEIPTS)
        results: list[s.LexofficeImportedItem] = []
        ok = failed = duplicates = 0
        errors: list[str] = []
        updated_at_from = body.updated_at_from.isoformat() if body.updated_at_from else None
        for page in range(body.max_pages):
            try:
                page_result = client.list_voucherlist(
                    page=page, updated_at_from=updated_at_from, voucher_type="purchaseinvoice"
                )
            except ProblemError as exc:
                failed += 1
                errors.append(str(exc.detail))
                break
            vouchers = page_result.get("content") or page_result.get("vouchers") or []
            if not vouchers:
                break
            for voucher in vouchers:
                voucher_id = str(voucher.get("id") or voucher.get("voucherId") or "")
                if not voucher_id:
                    continue
                existing_doc = await session.scalar(
                    select(Document).where(
                        Document.tenant_id == principal.tenant_id,
                        Document.source_system == "lexoffice",
                        Document.source_id == voucher_id,
                    )
                )
                if existing_doc is not None:
                    duplicates += 1
                    existing_draft = await session.scalar(
                        select(ReceiptDraft).where(ReceiptDraft.document_id == existing_doc.id)
                    )
                    results.append(
                        s.LexofficeImportedItem(
                            lexoffice_voucher_id=voucher_id,
                            ok=True,
                            duplicate=True,
                            receipt_draft_id=existing_draft.id if existing_draft else None,
                        )
                    )
                    continue
                try:
                    import json as _json

                    raw = _json.dumps(voucher, ensure_ascii=False).encode("utf-8")
                    document = await store_document(
                        session,
                        blobs,
                        tenant_id=principal.tenant_id,
                        data=raw,
                        title=f"lexoffice Beleg {voucher_id}",
                        filename=f"lexoffice-{voucher_id}.json",
                        mime_type="application/json",
                        source=DocumentSource.IMPORT,
                        category_id=None,
                        links=[],
                        created_by=principal.user_id,
                        scan_for_malware=False,
                    )
                    document.source_system = "lexoffice"
                    document.source_id = voucher_id
                    # Passthrough only, field names not fully verified (module doc); the
                    # reviewer sees the raw lexoffice data, never an invented mapping.
                    fields: dict[str, Any] = {
                        "lexoffice_raw": {"value": voucher, "confidence": None, "source": "local"}
                    }
                    for key, field_name in (
                        ("voucherNumber", "invoice_number"),
                        ("voucherDate", "invoice_date"),
                        ("totalGrossAmount", "gross_amount"),
                    ):
                        if voucher.get(key) is not None:
                            fields[field_name] = {
                                "value": voucher[key],
                                "confidence": None,
                                "source": "local",
                            }
                    draft = ReceiptDraft(
                        tenant_id=principal.tenant_id,
                        document_id=document.id,
                        source=ReceiptDraftSource.LEXOFFICE.value,
                        status=ReceiptDraftStatus.PROPOSED.value,
                        fields=fields,
                        warnings=[
                            "Aus lexoffice importiert; Felder sind ungeprüfte Rohdaten "
                            "(docs/integrations/lexoffice.md)."
                        ],
                    )
                    session.add(draft)
                    await session.flush()
                except ProblemError as exc:
                    failed += 1
                    errors.append(f"voucher {voucher_id}: {exc.detail}")
                    results.append(
                        s.LexofficeImportedItem(
                            lexoffice_voucher_id=voucher_id, ok=False, error=str(exc.detail)
                        )
                    )
                    continue
                ok += 1
                results.append(
                    s.LexofficeImportedItem(
                        lexoffice_voucher_id=voucher_id, ok=True, receipt_draft_id=draft.id
                    )
                )
            paging = page_result.get("paging") or {}
            if page >= int(paging.get("totalPages", page + 1)) - 1:
                break
        await _finish_run(
            session, run, {"ok": ok, "failed": failed, "duplicates": duplicates}, errors
        )
        return s.LexofficeImportResult(run_id=run.id, items=results)
