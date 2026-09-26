"""Celery jobs of the objektakte takeover, M35 Stufe 5 (docs/plans/M35-objektakte-uebernahme.md
section 4, paralleler Betrieb): the daily differential import of the complete objektakte
export, per tenant and only when that tenant has switched it on
(`ObjektakteSyncState.enabled`, default off, never a global override, ADR 0003).

The export itself is a `mysqldump` file objektakte writes to the worker's file system
(`ObjektakteSyncState.dump_path`, operator setup); the CRM never connects to the objektakte
database. Each tenant runs in its own transaction: a failed run rolls back and leaves that
tenant's water mark untouched, the failure is recorded on the sync state, and the next tenant
still runs. Same engine/transaction pattern as `mhvp.banking.tasks`.
"""

import asyncio
import logging
import posixpath
import uuid
from pathlib import Path, PurePosixPath

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.objektakte import objektakte_import as importer
from mhvp.objektakte.models import ObjektakteSyncState
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)
# Default of Settings.objektakte_dump_max_bytes; the file is read completely for parsing.
MAX_DUMP_BYTES = 512 * 1024 * 1024


class DumpUnreadableError(RuntimeError):
    """The configured export file is missing, not a `.sql` file, too large or not UTF-8."""


def path_within_dump_dir(dump_path: str, base_dir: str) -> bool:
    """True when ``dump_path`` (normalised, no ``..`` escape) lies inside ``base_dir``. Pure
    path arithmetic, no file system access, so the API can check a path that only exists on
    the worker."""
    base = PurePosixPath(posixpath.normpath(base_dir))
    candidate = PurePosixPath(posixpath.normpath(dump_path))
    return candidate != base and candidate.is_relative_to(base)


def read_dump_file(dump_path: str | None, base_dir: str, max_bytes: int = MAX_DUMP_BYTES) -> str:
    """Reads the configured export. Only an absolute `.sql` path to a regular file inside
    ``base_dir`` (symlinks resolved) is accepted, so a tenant setting can never point the
    worker at an arbitrary file for parsing (another tenant's export, system files). The size
    is checked with ``stat`` against ``max_bytes`` before anything is read into memory."""
    if not dump_path:
        raise DumpUnreadableError("Kein Exportpfad hinterlegt.")
    path = Path(dump_path)
    if not path.is_absolute() or path.suffix.lower() != ".sql":
        raise DumpUnreadableError("Der Exportpfad muss absolut sein und auf .sql enden.")
    if not path_within_dump_dir(dump_path, base_dir):
        raise DumpUnreadableError("Der Exportpfad liegt außerhalb des Exportverzeichnisses.")
    if not path.is_file():
        raise DumpUnreadableError("Die Exportdatei wurde nicht gefunden.")
    resolved = path.resolve()
    if not path_within_dump_dir(str(resolved), str(Path(base_dir).resolve())):
        raise DumpUnreadableError("Der Exportpfad liegt außerhalb des Exportverzeichnisses.")
    size = resolved.stat().st_size
    if size > max_bytes:
        raise DumpUnreadableError(
            f"Die Exportdatei ist zu groß ({size} Byte, Obergrenze {max_bytes} Byte)."
        )
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DumpUnreadableError("Die Exportdatei ist nicht als UTF-8 lesbar.") from exc


async def sync_tenant_once(
    settings: Settings, tenant_id: uuid.UUID, *, trigger: str, force: bool = False
) -> dict[str, int]:
    """One run for one tenant. `force` ignores `enabled`, never the water mark or the dump
    path; neither the beat job nor the queued manual trigger forces (the switch decides,
    Sicherheitsreview 26.09.2026, 7). The parameter stays for callers that must run a
    switched off tenant deliberately (tests, operator scripts)."""
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    counts = {"ran": 0, "skipped": 0, "failed": 0}
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            state = await session.scalar(
                select(ObjektakteSyncState).where(ObjektakteSyncState.tenant_id == tenant_id)
            )
            enabled = state is not None and (state.enabled or force)
            dump_path = state.dump_path if state is not None else None
        if not enabled:
            counts["skipped"] += 1
            return counts
        try:
            sql_text = read_dump_file(
                dump_path, settings.objektakte_dump_dir, settings.objektakte_dump_max_bytes
            )
            async with tenant_transaction(factory, tenant_id) as session:
                await importer.run_differential_import(
                    session, tenant_id, sql_text, trigger=trigger
                )
            counts["ran"] += 1
        except Exception as exc:  # recorded per tenant, other tenants continue
            log.warning("objektakte sync failed for tenant %s: %s", tenant_id, exc)
            counts["failed"] += 1
            async with tenant_transaction(factory, tenant_id) as session:
                await importer.record_failed_run(
                    session, tenant_id, trigger=trigger, error=str(exc)
                )
    finally:
        await engine.dispose()
    return counts


async def sync_all_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
    finally:
        await engine.dispose()
    totals = {"tenants": len(ids), "ran": 0, "skipped": 0, "failed": 0}
    for tenant_id in ids:
        for key, value in (await sync_tenant_once(settings, tenant_id, trigger="beat")).items():
            totals[key] += value
    return totals


@shared_task(name="mhvp.objektakte.sync_all")
def sync_all() -> dict[str, int]:
    """Celery beat entry (daily, `mhvp.worker`): only tenants with `ObjektakteSyncState.enabled`
    run; every other tenant is counted as skipped."""
    return asyncio.run(sync_all_once(get_settings()))


@shared_task(name="mhvp.objektakte.sync_tenant")
def sync_tenant(tenant_id: str) -> dict[str, int]:
    """Queued by the manual trigger endpoint (`mhvp.objektakte.routers`); runs the configured
    export for this tenant only while `ObjektakteSyncState.enabled` is on (the endpoint
    checks the switch as well, the job checks it again at run time)."""
    return asyncio.run(sync_tenant_once(get_settings(), uuid.UUID(tenant_id), trigger="manual"))
