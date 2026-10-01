"""Full tenant export as a background job (M27-01, 5.3).

The approved request (four eyes, ``market_readiness``) is processed on the worker: JSON lines
per entity plus the document originals from the object store are streamed into a ZIP on disk
(no full copy in memory) and the finished archive is stored under ``tenants/<id>/exports/``.
Every read happens in the tenant transaction (RLS). Secrets are never exported (see
``row_to_dict``). The archive is a draft; completeness and legal basis of the disclosure are
checked by the operator."""

import json
import logging
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.market_readiness import TenantExportRequest, row_to_dict

log = logging.getLogger(__name__)

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_READY = "ready"
JOB_FAILED = "failed"
BATCH = 500


def export_key(tenant_id: uuid.UUID, request_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/exports/{request_id}.zip"


def _entities() -> list[tuple[str, Any]]:
    from mhvp.accounting.models import (
        Invoice,
        InvoiceLine,
        JournalEntry,
        JournalLine,
        OpenItem,
        OpenItemSettlement,
    )
    from mhvp.banking.models import BankTransaction
    from mhvp.contacts.models import Contact
    from mhvp.contracts.models import Contract
    from mhvp.documents.models import Document
    from mhvp.properties.models import LegalEntity, Property, PropertyBankAccount, Unit
    from mhvp.tickets.models import Ticket, TicketComment

    return [
        ("legal_entities", LegalEntity),
        ("properties", Property),
        ("units", Unit),
        ("contacts", Contact),
        ("contracts", Contract),
        ("journal_entries", JournalEntry),
        ("journal_lines", JournalLine),
        ("invoices", Invoice),
        ("invoice_lines", InvoiceLine),
        ("open_items", OpenItem),
        ("open_item_settlements", OpenItemSettlement),
        ("bank_accounts", PropertyBankAccount),
        ("bank_transactions", BankTransaction),
        ("tickets", Ticket),
        ("ticket_comments", TicketComment),
        ("documents", Document),
    ]


async def _write_entity(
    session: AsyncSession, archive: zipfile.ZipFile, name: str, model: Any
) -> int:
    """One JSON line per row, keyset paged by id so that large tables stay out of memory."""
    count = 0
    last: uuid.UUID | None = None
    with archive.open(f"data/{name}.jsonl", "w") as handle:
        while True:
            query = select(model).order_by(model.id).limit(BATCH)
            if last is not None:
                query = query.where(model.id > last)
            rows = (await session.scalars(query)).all()
            if not rows:
                break
            for row in rows:
                line = json.dumps(row_to_dict(row), ensure_ascii=False)
                handle.write(line.encode() + b"\n")
            count += len(rows)
            last = rows[-1].id
            session.expunge_all()
    return count


def _safe_name(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in value)
    return cleaned[:120] or "datei"


async def _write_documents(
    session: AsyncSession, archive: zipfile.ZipFile, client: Any, bucket: str
) -> dict[str, Any]:
    """Originals of the object store; each failure is listed, never silently dropped."""
    from mhvp.documents.models import Document, StorageKind

    written = 0
    bytes_total = 0
    errors: list[dict[str, str]] = []
    skipped_external = 0
    last: uuid.UUID | None = None
    while True:
        query = select(Document).order_by(Document.id).limit(BATCH)
        if last is not None:
            query = query.where(Document.id > last)
        rows = (await session.scalars(query)).all()
        if not rows:
            break
        last = rows[-1].id
        for doc in rows:
            if doc.storage != StorageKind.MINIO:
                skipped_external += 1
                continue
            try:
                body = client.get_object(Bucket=bucket, Key=doc.storage_ref)["Body"]
                with archive.open(f"documents/{doc.id}_{_safe_name(doc.filename)}", "w") as out:
                    while chunk := body.read(1024 * 1024):
                        out.write(chunk)
                        bytes_total += len(chunk)
                written += 1
            except Exception as exc:  # list and go on, the operator decides on gaps
                errors.append({"document_id": str(doc.id), "error": type(exc).__name__})
        session.expunge_all()
    return {
        "written": written,
        "bytes": bytes_total,
        "external_storage_not_exported": skipped_external,
        "errors": errors,
    }


async def build_full_export(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    purpose: str,
    target: Path,
    client: Any,
    bucket: str,
) -> dict[str, Any]:
    """Writes the archive to ``target`` and returns the manifest."""
    from mhvp.platform.models import Tenant, TenantSettings

    counts: dict[str, int] = {}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        async with tenant_transaction(factory, tenant_id) as session:
            tenant = await session.get(Tenant, tenant_id)
            if tenant is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            archive.writestr(
                "data/tenant.json", json.dumps(row_to_dict(tenant), ensure_ascii=False, indent=2)
            )
            settings = await session.scalar(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
            )
            if settings is not None:
                archive.writestr(
                    "data/tenant_settings.json",
                    json.dumps(
                        {"company": settings.company, "branding": settings.branding},
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            for name, model in _entities():
                counts[name] = await _write_entity(session, archive, name, model)
            documents = await _write_documents(session, archive, client, bucket)
        manifest = {
            "tenant_id": str(tenant_id),
            "purpose": purpose,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "draft",
            "format": "jsonl per entity under data/, originals under documents/",
            "entities": counts,
            "documents": documents,
            "note": "Entwurf; Vollständigkeit und Rechtsgrundlage prüft der Betreiber.",
        }
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


async def run_export_job(settings: Settings, request_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    from mhvp.core.storage import create_s3_client

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportRequest, request_id)
            if row is None or row.tenant_id != tenant_id or row.status != "approved":
                return "skipped"
            if row.job_status in (JOB_RUNNING, JOB_READY):
                return "skipped"
            row.job_status = JOB_RUNNING
            row.job_error = None
            purpose = row.purpose
        workdir = Path(tempfile.mkdtemp(prefix="mhvp-export-"))
        try:
            target = workdir / "export.zip"
            client = create_s3_client(settings)
            await build_full_export(factory, tenant_id, purpose, target, client, settings.s3_bucket)
            digest = sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            key = export_key(tenant_id, request_id)
            client.upload_file(str(target), settings.s3_bucket, key)
            size = target.stat().st_size
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportRequest, request_id)
            if row is not None:
                row.job_status = JOB_READY
                row.job_object_key = key
                row.job_size = size
                row.job_sha256 = digest.hexdigest()
                row.job_finished_at = datetime.now(UTC)
        return JOB_READY
    except Exception as exc:
        log.error("tenant export job failed: %s", type(exc).__name__)
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportRequest, request_id)
            if row is not None:
                row.job_status = JOB_FAILED
                row.job_error = f"{type(exc).__name__}: {exc}"[:2000]
                row.job_finished_at = datetime.now(UTC)
        raise
    finally:
        await engine.dispose()


def dispatch_export_job(request_id: str, tenant_id: str) -> None:
    """Hands the request to the worker after the queuing transaction committed. Module level
    so that tests replace it (see ``accounting.audit_export_routers.dispatch_audit_export``)."""
    tenant_export_job.delay(request_id, tenant_id)


@shared_task(name="mhvp.platform.tenant_export")
def tenant_export_job(request_id: str, tenant_id: str) -> str:
    import asyncio

    return asyncio.run(run_export_job(get_settings(), uuid.UUID(request_id), uuid.UUID(tenant_id)))


# ---------------------------------------------------------------------------------------
# Tenant administrator export (M2-01): own job table, no four eyes request
# ---------------------------------------------------------------------------------------


def tenant_export_key(tenant_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/exports/job-{job_id}.zip"


async def run_tenant_export_job(settings: Settings, job_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    from mhvp.core.events import emit
    from mhvp.core.storage import create_s3_client
    from mhvp.platform.models import TenantExportJob

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportJob, job_id)
            if row is None or row.tenant_id != tenant_id or row.status != JOB_QUEUED:
                return "skipped"
            row.status = JOB_RUNNING
            row.error = None
            row.started_at = datetime.now(UTC)
        workdir = Path(tempfile.mkdtemp(prefix="mhvp-export-"))
        try:
            target = workdir / "export.zip"
            client = create_s3_client(settings)
            manifest = await build_full_export(
                factory, tenant_id, "full", target, client, settings.s3_bucket
            )
            digest = sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            key = tenant_export_key(tenant_id, job_id)
            client.upload_file(str(target), settings.s3_bucket, key)
            size = target.stat().st_size
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportJob, job_id)
            if row is not None:
                row.status = JOB_READY
                row.object_key = key
                row.size = size
                row.sha256 = digest.hexdigest()
                row.manifest = manifest
                row.finished_at = datetime.now(UTC)
                await emit(
                    session,
                    tenant_id=tenant_id,
                    type="tenant_export.finished",
                    entity_type="tenant_export_job",
                    entity_id=job_id,
                    actor_user_id=row.requested_by,
                    payload={"size": size, "sha256": row.sha256},
                )
        return JOB_READY
    except Exception as exc:
        log.error("tenant export job failed: %s", type(exc).__name__)
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.get(TenantExportJob, job_id)
            if row is not None:
                row.status = JOB_FAILED
                row.error = f"{type(exc).__name__}: {exc}"[:2000]
                row.finished_at = datetime.now(UTC)
        raise
    finally:
        await engine.dispose()


def dispatch_tenant_export_job(job_id: str, tenant_id: str) -> None:
    """Module level so that tests replace it."""
    tenant_export_admin_job.delay(job_id, tenant_id)


@shared_task(name="mhvp.platform.tenant_export_job")
def tenant_export_admin_job(job_id: str, tenant_id: str) -> str:
    import asyncio

    return asyncio.run(
        run_tenant_export_job(get_settings(), uuid.UUID(job_id), uuid.UUID(tenant_id))
    )
