"""Settings page "Einstellungen, Schnittstellen" for lexoffice (M13-lexoffice): connection
config, connection test, run protocol, explicit export (invoices, contacts) and explicit
import (receipts). Nothing here runs on a schedule or automatically; every export and import
is one logged, operator triggered call (rule 0.1.1, 0.1.4, 0.1.6).

Export needs release gate G1 (productive bookkeeping) open for the tenant in addition to the
``LexofficeTenantConfig.enabled`` flag; both default closed (ADR 0003). Import only creates a
``ReceiptDraft`` (never a posting), so it needs the feature flag but not G1.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice
from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, require_release_gate
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentSource
from mhvp.documents.services import store_document
from mhvp.integrations import schemas as s
from mhvp.integrations.lexoffice import (
    LexofficeClient,
    LexofficeCredentials,
    strict_hosts,
    validate_base_url,
)
from mhvp.integrations.live_mode import ensure_live_allowed, resolver_of
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeExportKind,
    LexofficeExportLink,
    LexofficeLinkStatus,
    LexofficeRunKind,
    LexofficeRunStatus,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)
from mhvp.receipts.models import ReceiptDraft, ReceiptDraftSource, ReceiptDraftStatus

router = APIRouter(prefix="/integrations/lexoffice", tags=["Schnittstellen"])

SETTINGS = require_permission("tenant_settings:update")
SETTINGS_READ = require_permission("tenant_settings:read")
EXPORT = require_permission("accounting:create")
IMPORT = require_permission("accounting:create")
READ = require_permission("accounting:read")
G1 = require_release_gate(ReleaseGate.G1)


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


async def _config(session: AsyncSession, tenant_id: uuid.UUID) -> LexofficeTenantConfig | None:
    """The tenant default config (``legal_entity_id IS NULL``); the legacy endpoints of this
    module are aliases of it (rule INT-LEXO-01, several organisations per tenant)."""
    result: LexofficeTenantConfig | None = await session.scalar(
        select(LexofficeTenantConfig).where(
            LexofficeTenantConfig.tenant_id == tenant_id,
            LexofficeTenantConfig.legal_entity_id.is_(None),
        )
    )
    return result


def _base_url(request: Request, url: str) -> str:
    """GAL-202: the API key only goes to an allowed Lexware host (strict in staging/prod)."""
    return validate_base_url(url, strict=strict_hosts(request.app.state.settings))


def _client_for(config: LexofficeTenantConfig, request: Request) -> LexofficeClient:
    if not config.enabled or not config.api_key:
        raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
    return LexofficeClient(
        LexofficeCredentials(api_key=config.api_key, base_url=_base_url(request, config.base_url))
    )


def _idempotency_key(tenant_id: uuid.UUID, kind: LexofficeExportKind, entity_id: uuid.UUID) -> str:
    return hashlib.sha256(f"{tenant_id}:{kind.value}:{entity_id}".encode()).hexdigest()


UNKNOWN = "unknown"
EXPORTED = "exported"
UNKNOWN_DETAIL = (
    "Der frühere Export hat keine Antwort erhalten und wurde möglicherweise verarbeitet. "
    "Bitte in Lexware Office prüfen und gegebenenfalls ausdrücklich erneut exportieren."
)


def _reconcile_voucher(
    client: LexofficeClient, link: LexofficeExportLink, payload: Any
) -> str | None:
    """Look up a voucher whose create timed out by its voucher number (GAL-201). Returns the
    Lexware id when exactly one voucher carries that number, else ``None``."""
    number = link.voucher_number
    if not number:
        return None
    voucher_type = payload.get("type") if isinstance(payload, dict) else None
    try:
        found = client.list_voucherlist(
            voucher_type if isinstance(voucher_type, str) and voucher_type else "any",
            "any",
            voucher_number=number,
        )
    except ProblemError:
        return None
    hits = [
        str(v.get("id") or v.get("voucherId"))
        for v in (found.get("content") or [])
        if isinstance(v, dict)
        and v.get("voucherNumber") == number
        and (v.get("id") or v.get("voucherId"))
    ]
    return hits[0] if len(hits) == 1 else None


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
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
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
            config.base_url = _base_url(request, body.base_url)
        if body.api_key is not None:
            config.api_key = body.api_key.strip()
            config.api_key_last4 = config.api_key[-4:]
            config.token_invalid = False
        config.enabled = body.enabled
        if config.enabled and not config.api_key:
            raise _invalid("Ohne API-Schlüssel kann die Anbindung nicht aktiviert werden.")
        if config.enabled and config.avv_confirmed_on is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_AVV_MISSING)
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
        await ensure_live_allowed(session, principal.tenant_id, "lexoffice", resolver_of(request))
        run = await _run(session, principal, LexofficeRunKind.TEST)
        client = LexofficeClient(
            LexofficeCredentials(
                api_key=config.api_key, base_url=_base_url(request, config.base_url)
            )
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


@router.get("/runs", summary="Letzte Läufe", dependencies=[Depends(strict_query)])
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


async def _export_one(
    session: AsyncSession,
    client: LexofficeClient,
    principal: TenantPrincipal,
    run: LexofficeSyncRun,
    kind: LexofficeExportKind,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
    force: bool,
) -> s.LexofficeExportResultItem:
    """Export one entity idempotently (GAL-201).

    - An ``exported`` link answers with the stored Lexware id (no second POST) unless ``force``.
    - An ``unknown`` link (earlier POST timed out) never triggers a blind second POST: vouchers
      are looked up by voucher number and adopted when exactly one matches; otherwise the item
      stays ``outcome_unknown`` until the operator re-exports with ``force``.
    - A POST that times out leaves an ``unknown`` link instead of no trace.
    """
    existing = await _already_exported(session, principal.tenant_id, kind, entity_id)
    key = _idempotency_key(principal.tenant_id, kind, entity_id)
    if existing is not None and not force:
        if existing.status != UNKNOWN and existing.lexoffice_id:
            return s.LexofficeExportResultItem(
                entity_id=entity_id,
                ok=True,
                lexoffice_id=existing.lexoffice_id,
                skipped_duplicate=True,
                idempotency_key=key,
            )
        adopted = (
            _reconcile_voucher(client, existing, payload)
            if kind == LexofficeExportKind.INVOICE
            else None
        )
        if adopted is None:
            return s.LexofficeExportResultItem(
                entity_id=entity_id,
                ok=False,
                error=UNKNOWN_DETAIL,
                outcome_unknown=True,
                error_code=ErrorCodes.LEXOFFICE_OUTCOME_UNKNOWN.code,
                idempotency_key=key,
            )
        existing.lexoffice_id = adopted
        existing.status = EXPORTED
        existing.run_id = run.id
        await session.flush()
        return s.LexofficeExportResultItem(
            entity_id=entity_id,
            ok=True,
            lexoffice_id=adopted,
            skipped_duplicate=True,
            reconciled=True,
            idempotency_key=key,
        )
    number = payload.get("voucherNumber") if kind == LexofficeExportKind.INVOICE else None
    voucher_number = number[:64] if isinstance(number, str) and number else None
    try:
        if kind == LexofficeExportKind.INVOICE:
            created = client.create_voucher(payload)
            lexoffice_id = str(created.get("id") or created.get("voucherId") or "")
        else:
            created = client.create_contact(payload)
            lexoffice_id = str(created.get("id") or "")
        if not lexoffice_id:
            raise ProblemError(
                ErrorCodes.LEXOFFICE_UNAVAILABLE, detail="lexoffice-Antwort enthielt keine ID."
            )
    except ProblemError as exc:
        maybe = bool(exc.extensions.get("maybe_processed"))
        if maybe:
            if existing is None:
                existing = LexofficeExportLink(
                    tenant_id=principal.tenant_id,
                    entity_kind=kind.value,
                    entity_id=entity_id,
                )
                session.add(existing)
            existing.status = UNKNOWN
            existing.lexoffice_id = None
            existing.run_id = run.id
            existing.idempotency_key = key
            existing.voucher_number = voucher_number
            await session.flush()
        return s.LexofficeExportResultItem(
            entity_id=entity_id,
            ok=False,
            error=UNKNOWN_DETAIL if maybe else str(exc.detail),
            outcome_unknown=maybe,
            error_code=(ErrorCodes.LEXOFFICE_OUTCOME_UNKNOWN if maybe else exc.error).code,
            idempotency_key=key,
        )
    if existing is None:
        existing = LexofficeExportLink(
            tenant_id=principal.tenant_id, entity_kind=kind.value, entity_id=entity_id
        )
        session.add(existing)
    existing.lexoffice_id = lexoffice_id
    existing.status = EXPORTED
    existing.run_id = run.id
    existing.idempotency_key = key
    existing.voucher_number = voucher_number
    await session.flush()
    return s.LexofficeExportResultItem(
        entity_id=entity_id, ok=True, lexoffice_id=lexoffice_id, idempotency_key=key
    )


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
        client = _client_for(config, request) if config else None
        if client is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        await ensure_live_allowed(session, principal.tenant_id, "lexoffice", resolver_of(request))
        run = await _run(session, principal, LexofficeRunKind.EXPORT_INVOICES)
        results: list[s.LexofficeExportResultItem] = []
        ok = failed = unknown = 0
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
            result = await _export_one(
                session,
                client,
                principal,
                run,
                LexofficeExportKind.INVOICE,
                item.invoice_id,
                item.payload,
                item.force,
            )
            results.append(result)
            if result.ok:
                ok += 1
            else:
                failed += 1
                unknown += int(result.outcome_unknown)
                errors.append(f"invoice {item.invoice_id}: {result.error}")
        await _finish_run(session, run, {"ok": ok, "failed": failed, "unknown": unknown}, errors)
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
        client = _client_for(config, request) if config else None
        if client is None or config is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        await ensure_live_allowed(session, principal.tenant_id, "lexoffice", resolver_of(request))
        run = await _run(session, principal, LexofficeRunKind.EXPORT_CONTACTS)
        results: list[s.LexofficeExportResultItem] = []
        ok = failed = unknown = 0
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
            result = await _export_one(
                session,
                client,
                principal,
                run,
                LexofficeExportKind.CONTACT,
                item.contact_id,
                item.payload,
                item.force,
            )
            results.append(result)
            if not result.ok or result.skipped_duplicate:
                if result.ok:
                    ok += 1
                else:
                    failed += 1
                    unknown += int(result.outcome_unknown)
                    errors.append(f"contact {item.contact_id}: {result.error}")
                continue
            lexoffice_id = str(result.lexoffice_id)
            # One truth for contacts going forward (ADR 0015): the contact link table.
            link = await session.scalar(
                select(LexofficeContactLink).where(
                    LexofficeContactLink.config_id == config.id,
                    LexofficeContactLink.contact_id == item.contact_id,
                )
            )
            if link is None:
                link = LexofficeContactLink(
                    tenant_id=principal.tenant_id,
                    config_id=config.id,
                    contact_id=item.contact_id,
                    sync_status=LexofficeLinkStatus.LINKED.value,
                    match_reason="export_migrated",
                )
                session.add(link)
            link.lexoffice_contact_id = lexoffice_id
            link.sync_status = LexofficeLinkStatus.LINKED.value
            ok += 1
        await _finish_run(session, run, {"ok": ok, "failed": failed, "unknown": unknown}, errors)
        return s.LexofficeExportResult(run_id=run.id, items=results)


@router.post("/import/receipts", summary="Belege aus lexoffice als Belegentwurf importieren")
async def import_receipts(
    body: s.LexofficeImportReceiptsIn,
    request: Request,
    principal: TenantPrincipal = Depends(IMPORT),
) -> s.LexofficeImportResult:
    async with tenant_tx(request, principal) as session:
        config = await _config(session, principal.tenant_id)
        client = _client_for(config, request) if config else None
        if client is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_NOT_CONFIGURED)
        blobs = BlobStore(request.app.state.settings)
        run = await _run(session, principal, LexofficeRunKind.IMPORT_RECEIPTS)
        results: list[s.LexofficeImportedItem] = []
        ok = failed = duplicates = 0
        errors: list[str] = []
        # Additive per ADR 0009: the datetime is truncated to the documented yyyy-MM-dd date
        # in Europe/Berlin (docs/integrations/lexoffice.md, voucherlist filters).
        updated_date_from = (
            body.updated_at_from.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()
            if body.updated_at_from
            else None
        )
        for page in range(body.max_pages):
            try:
                page_result = client.list_voucherlist(
                    "purchaseinvoice",
                    body.voucher_status,
                    page=page,
                    updated_date_from=updated_date_from,
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
