"""Unvalidated CHECK constraints as consistency finding (AO07, AN14-07).

Migrations such as 0449 add CHECK constraints ``NOT VALID`` when existing rows violate them.
This module lists those constraints (``pg_constraint.convalidated = false``) with the number
of violating rows visible to the tenant (RLS applies) and offers to validate them. Validation
runs ``VALIDATE CONSTRAINT`` in one transaction on the migration role (the runtime role does
not own the tables); a violation gives 409 with the list and changes nothing.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.accounting.audit_events import record_change
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.config import get_settings
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/platform/constraint-checks", tags=["Plattform"])

HINT = (
    "Die Prüfregel gilt für neue Zeilen, Bestandsdaten sind nicht geprüft. Verstöße korrigieren "
    "und danach über POST /platform/constraint-checks/validate validieren (Administrator)."
)

_LIST = text(
    """
    SELECT c.conname AS name, c.conrelid::regclass::text AS table_name,
           quote_ident(c.conname) AS qname, c.conrelid::regclass AS rel,
           pg_get_expr(c.conbin, c.conrelid) AS expr
      FROM pg_constraint c
      JOIN pg_namespace n ON n.oid = c.connamespace
     WHERE c.contype = 'c' AND NOT c.convalidated AND n.nspname = current_schema()
     ORDER BY c.conrelid::regclass::text, c.conname
    """
)


class UnvalidatedConstraintOut(BaseModel):
    constraint: str
    table: str
    violations: int


class ConstraintCheckOut(BaseModel):
    ok: bool
    constraints: list[UnvalidatedConstraintOut]
    hint: str | None = None


async def unvalidated_constraints(session: AsyncSession) -> list[dict[str, Any]]:
    """Findings: one entry per unvalidated CHECK with the violations visible to the tenant.
    Table and condition come from the catalog, never from user input."""
    rows = (await session.execute(_LIST)).mappings().all()
    findings: list[dict[str, Any]] = []
    for r in rows:
        count = await session.scalar(
            text(f"SELECT count(*) FROM {r['table_name']} WHERE NOT ({r['expr']})")  # noqa: S608
        )
        findings.append(
            {"constraint": r["name"], "table": r["table_name"], "violations": int(count or 0)}
        )
    return findings


def _out(findings: list[dict[str, Any]]) -> ConstraintCheckOut:
    return ConstraintCheckOut(
        ok=not findings,
        constraints=[UnvalidatedConstraintOut(**f) for f in findings],
        hint=HINT if findings else None,
    )


@router.get(
    "",
    summary="Nicht validierte Prüfregeln (NOT VALID) mit Zahl der Verstöße",
    dependencies=[Depends(strict_query)],
)
async def get_constraint_checks(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> ConstraintCheckOut:
    async with tenant_tx(request, principal) as session:
        return _out(await unvalidated_constraints(session))


@router.post("/validate", summary="Nicht validierte Prüfregeln validieren (Administrator)")
async def validate_constraints(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> ConstraintCheckOut:
    """Runs ``VALIDATE CONSTRAINT`` for every unvalidated CHECK in one transaction. On a
    violation nothing is validated and the answer is 409 with the list."""
    async with tenant_tx(request, principal) as session:
        before = await unvalidated_constraints(session)
        if not before:
            return _out([])
        names = (await session.execute(_LIST)).mappings().all()
        targets = [(r["table_name"], r["qname"]) for r in names]
    url = get_settings().migration_database_url
    if url is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Keine Migrationsverbindung konfiguriert, Validierung nicht möglich.",
            status=503,
        )
    engine = create_async_engine(url.get_secret_value(), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for table, qname in targets:
                await conn.execute(text(f"ALTER TABLE {table} VALIDATE CONSTRAINT {qname}"))
    except (ProgrammingError, DBAPIError) as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        if sqlstate != "23514":
            raise
        raise ProblemError(
            ErrorCodes.CONSTRAINT_VIOLATIONS,
            detail=HINT,
            extensions={"constraints": before},
        ) from exc
    finally:
        await engine.dispose()
    async with tenant_tx(request, principal) as session:
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            type="constraint_checks.validated",
            entity_type="tenant_settings",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            before={"constraints": before},
            after={"constraints": []},
        )
        return _out(await unvalidated_constraints(session))
