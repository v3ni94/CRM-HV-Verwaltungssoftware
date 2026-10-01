"""Generic master key rotation for encrypted fields (section 3.5, S16-03, ADR 0006).

Every column of type :class:`mhvp.core.crypto.EncryptedText` is found on ``Base.metadata``;
nothing is registered by hand, so a new encrypted field is rotated without a code change.
The tenant keys are derived from the master key (HKDF per scope), so rotating the master key
rotates every tenant key and the platform scope in one run.

Procedure (per tenant in its own RLS bound transaction, platform tables in a platform
transaction, every table in a savepoint):

1. Read the raw ciphertext (bypassing the column type), take the scope from its header.
2. Ciphertext that already opens with the new key counts as ``already_rotated`` (a run that
   stopped halfway can simply be repeated). Otherwise decrypt with the old key, encrypt with
   the new key, verify the round trip in memory and write it back. ``updated_at`` is kept, the
   content does not change (rule 0.1.7: no financial content is altered).
3. Keyed fingerprints (HMAC, also derived from the master key) are recomputed when the table
   has a column ``<column>_fingerprint`` next to the encrypted ``<column>``. The stored value
   must match the old key first; a mismatch is recorded and the row is not written.
4. Fingerprint columns without an encrypted partner and ciphertext embedded in JSON
   (``secret_enc``) cannot be recomputed generically: when they hold values, apply mode stops
   before writing anything (fail closed) and the protocol names them.

What it never does: log, print or write plaintext or a key; take keys from the command line
(process list); write anything in ``--dry-run`` mode. Keys come from ``MHVP_OLD_MASTER_KEY``
and ``MHVP_NEW_MASTER_KEY`` (base64 of 32 bytes). After a successful apply run the operator
switches ``MHVP_MASTER_KEY`` to the new key and restarts API and worker; the old key is kept
until the backup retention of the old ciphertext has expired (operations decision).

The protocol (JSON) holds counts per table, column and scope plus the sha256 of the key
fingerprints (never the keys) and the start and end time.

CLI: ``python -m mhvp.core.key_rotation --dry-run --protocol rotation.json``.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, LargeBinary, String, Table, bindparam, cast, func, select, type_coerce
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core import crypto
from mhvp.core.db.base import Base

log = logging.getLogger(__name__)

OLD_KEY_ENV = "MHVP_OLD_MASTER_KEY"
NEW_KEY_ENV = "MHVP_NEW_MASTER_KEY"
EMBEDDED_KEYS: tuple[str, ...] = ("secret_enc",)
FINGERPRINT_SUFFIX = "fingerprint"
BATCH = 500


class RotationError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    table: Table
    columns: tuple[str, ...]
    fingerprints: dict[str, str]  # encrypted column -> fingerprint column

    @property
    def tenant_scoped(self) -> bool:
        return "tenant_id" in self.table.c


@dataclass
class RotationReport:
    dry_run: bool
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    old_key_sha256: str = ""
    new_key_sha256: str = ""
    counts: Counter[str] = field(default_factory=Counter)
    rows: dict[str, Counter[str]] = field(default_factory=dict)
    blockers: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def add(self, key: str, status: str, n: int = 1) -> None:
        self.rows.setdefault(key, Counter())[status] += n
        self.counts[status] += n

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "old_key_sha256": self.old_key_sha256,
            "new_key_sha256": self.new_key_sha256,
            "counts": dict(self.counts),
            "rows": {k: dict(v) for k, v in sorted(self.rows.items())},
            "blockers": self.blockers,
            "errors": self.errors,
        }

    @property
    def ok(self) -> bool:
        return not self.errors and not self.blockers and not self.counts.get("mismatch")


def discover_targets(metadata: Any = None) -> list[Target]:
    """All tables with at least one ``EncryptedText`` column, sorted by name."""
    metadata = metadata or Base.metadata
    targets = []
    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        columns = tuple(c.name for c in table.c if isinstance(c.type, crypto.EncryptedText))
        if not columns or "id" not in table.c:
            continue
        fingerprints = {
            col: f"{col}_{FINGERPRINT_SUFFIX}"
            for col in columns
            if f"{col}_{FINGERPRINT_SUFFIX}" in table.c
        }
        targets.append(Target(table=table, columns=columns, fingerprints=fingerprints))
    return targets


def unpaired_fingerprint_columns(metadata: Any = None) -> list[tuple[Table, str]]:
    """Fingerprint columns whose plaintext is not an encrypted column of the same table."""
    metadata = metadata or Base.metadata
    found = []
    for table in sorted(metadata.tables.values(), key=lambda t: t.name):
        encrypted = {c.name for c in table.c if isinstance(c.type, crypto.EncryptedText)}
        for c in table.c:
            if not c.name.endswith(FINGERPRINT_SUFFIX) or not isinstance(c.type, String):
                continue
            partner = c.name.removesuffix(f"_{FINGERPRINT_SUFFIX}")
            if partner not in encrypted:
                found.append((table, c.name))
    return found


def json_columns(metadata: Any = None) -> list[tuple[Table, str]]:
    metadata = metadata or Base.metadata
    return [
        (table, c.name)
        for table in sorted(metadata.tables.values(), key=lambda t: t.name)
        for c in table.c
        if isinstance(c.type, JSON | JSONB)
    ]


def rotate_blob(
    old: bytes, new: bytes, blob: bytes
) -> tuple[str, bytes | None, str | None, str | None]:
    """Returns ``(status, new_ciphertext, plaintext, scope)``. The plaintext is only used in
    memory by the caller to recompute keyed fingerprints; it is never logged or stored."""
    scope = crypto.ciphertext_scope(blob)
    try:
        crypto.decrypt_with_master(new, blob)
        return "already_rotated", None, None, scope
    except crypto.CryptoError:
        pass
    plaintext = crypto.decrypt_with_master(old, blob)
    fresh = crypto.encrypt_with_master(new, plaintext, scope)
    if crypto.decrypt_with_master(new, fresh) != plaintext:  # pragma: no cover - defensive
        raise crypto.CryptoError("round trip failed")
    return "rotated", fresh, plaintext, scope


async def _count_nonnull(session: AsyncSession, table: Table, column: str) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(table).where(table.c[column].is_not(None))
        )
        or 0
    )


async def check_blockers(session: AsyncSession, report: RotationReport, scope: str) -> None:
    tenant = scope != crypto.PLATFORM_SCOPE
    for table, column in unpaired_fingerprint_columns():
        if ("tenant_id" in table.c) != tenant:
            continue
        n = await _count_nonnull(session, table, column)
        if n:
            report.blockers.append(
                {
                    "scope": scope,
                    "table": table.name,
                    "column": column,
                    "rows": n,
                    "reason": "fingerprint_without_encrypted_partner",
                }
            )
    for table, column in json_columns():
        if ("tenant_id" in table.c) != tenant:
            continue
        for key in EMBEDDED_KEYS:
            n = int(
                await session.scalar(
                    select(func.count())
                    .select_from(table)
                    .where(cast(table.c[column], String).contains(f'"{key}"'))
                )
                or 0
            )
            if n:
                report.blockers.append(
                    {
                        "scope": scope,
                        "table": table.name,
                        "column": column,
                        "rows": n,
                        "reason": f"embedded_ciphertext:{key}",
                    }
                )


async def rotate_target(
    session: AsyncSession,
    target: Target,
    old: bytes,
    new: bytes,
    report: RotationReport,
    *,
    dry_run: bool,
) -> None:
    table = target.table
    raw = [type_coerce(table.c[c], LargeBinary).label(c) for c in target.columns]
    fps = [table.c[f].label(f) for f in target.fingerprints.values()]
    last: Any = None
    while True:
        query = select(table.c.id, *raw, *fps).order_by(table.c.id).limit(BATCH)
        if last is not None:
            query = query.where(table.c.id > last)
        rows = (await session.execute(query)).mappings().all()
        if not rows:
            return
        for row in rows:
            last = row["id"]
            values: dict[str, Any] = {}
            for col in target.columns:
                blob = row[col]
                key = f"{table.name}.{col}"
                if blob is None:
                    continue
                try:
                    status, fresh, plaintext, scope = rotate_blob(old, new, bytes(blob))
                except crypto.CryptoError as exc:
                    report.add(key, "error")
                    report.errors.append(
                        {
                            "table": table.name,
                            "column": col,
                            "id": str(row["id"]),
                            "error": str(exc),
                        }
                    )
                    continue
                report.add(key, status)
                if fresh is None or plaintext is None or scope is None:
                    continue
                fp_col = target.fingerprints.get(col)
                if fp_col is not None and row[fp_col] is not None:
                    if row[fp_col] != crypto.fingerprint_with_master(old, plaintext, scope):
                        report.add(f"{table.name}.{fp_col}", "mismatch")
                        continue
                    values[fp_col] = crypto.fingerprint_with_master(new, plaintext, scope)
                    report.add(f"{table.name}.{fp_col}", "recomputed")
                values[col] = fresh
            if values and not dry_run:
                params: dict[str, Any] = {}
                for name, value in values.items():
                    if name in target.columns:
                        params[name] = type_coerce(
                            bindparam(f"v_{name}", value, type_=LargeBinary), LargeBinary
                        )
                    else:
                        params[name] = value
                if "updated_at" in table.c:
                    params["updated_at"] = table.c.updated_at
                await session.execute(
                    sa_update(table).where(table.c.id == row["id"]).values(**params)
                )


async def rotate_scope(
    session: AsyncSession,
    scope: str,
    old: bytes,
    new: bytes,
    report: RotationReport,
    *,
    dry_run: bool,
) -> None:
    tenant = scope != crypto.PLATFORM_SCOPE
    for target in discover_targets():
        if target.tenant_scoped != tenant:
            continue
        try:
            async with session.begin_nested():
                await rotate_target(session, target, old, new, report, dry_run=dry_run)
        except Exception as exc:  # grant or trigger refusal: record, continue with the rest
            report.errors.append(
                {"scope": scope, "table": target.table.name, "error": type(exc).__name__}
            )


async def run(
    session_factory: async_sessionmaker[AsyncSession],
    old: bytes,
    new: bytes,
    *,
    dry_run: bool,
    tenant_ids: list[uuid.UUID] | None = None,
    include_platform: bool = True,
) -> RotationReport:
    """``tenant_ids``/``include_platform`` narrow the run for tests only: a real rotation
    must cover every tenant and the platform scope (the CLI offers no narrowing), since the
    process uses one master key for all scopes."""
    from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
    from mhvp.platform.models import Tenant

    if old == new:
        raise RotationError("alter und neuer Schlüssel sind gleich")
    report = RotationReport(dry_run=dry_run)
    report.old_key_sha256 = hashlib.sha256(b"key-id:" + old).hexdigest()[:16]
    report.new_key_sha256 = hashlib.sha256(b"key-id:" + new).hexdigest()[:16]
    async with platform_transaction(session_factory) as session:
        tenants = tenant_ids or list((await session.scalars(select(Tenant.id))).all())
        if include_platform:
            await check_blockers(session, report, crypto.PLATFORM_SCOPE)
    for tenant_id in tenants:
        async with tenant_transaction(session_factory, tenant_id) as session:
            await check_blockers(session, report, str(tenant_id))
    effective_dry = dry_run or bool(report.blockers)
    if include_platform:
        async with platform_transaction(session_factory) as session:
            await rotate_scope(
                session, crypto.PLATFORM_SCOPE, old, new, report, dry_run=effective_dry
            )
    for tenant_id in tenants:
        async with tenant_transaction(session_factory, tenant_id) as session:
            await rotate_scope(session, str(tenant_id), old, new, report, dry_run=effective_dry)
    report.finished_at = datetime.now(UTC).isoformat()
    return report


def _key_from_env(name: str) -> bytes:
    value = os.environ.get(name)
    if not value:
        raise RotationError(f"{name} fehlt")
    try:
        return crypto.decode_master_key(value)
    except (crypto.CryptoError, ValueError) as exc:
        raise RotationError(f"{name} ist kein Base64-Schlüssel mit 32 Byte") from exc


async def run_cli(args: argparse.Namespace) -> int:
    import mhvp.models  # noqa: F401  (registers all mapped tables)
    from mhvp.core.config import get_settings
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    try:
        old, new = _key_from_env(OLD_KEY_ENV), _key_from_env(NEW_KEY_ENV)
    except RotationError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    engine = create_app_engine(get_settings())
    try:
        report = await run(create_session_factory(engine), old, new, dry_run=args.dry_run)
    except RotationError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    finally:
        await engine.dispose()
    if args.protocol:
        await asyncio.to_thread(
            Path(args.protocol).write_text,
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False),
            "utf-8",
        )
    print(  # noqa: T201
        json.dumps(
            {
                "dry_run": args.dry_run,
                "counts": dict(report.counts),
                "blockers": len(report.blockers),
                "errors": len(report.errors),
            }
        )
    )
    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.core.key_rotation",
        description="Verschlüsselte Felder aller Mandanten auf einen neuen Master-Key umstellen.",
    )
    parser.add_argument("--dry-run", action="store_true", help="nur prüfen, nichts schreiben")
    parser.add_argument("--protocol", help="Pfad der JSON-Protokolldatei (ohne Klartext)")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(run_cli(build_parser().parse_args(argv)))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
