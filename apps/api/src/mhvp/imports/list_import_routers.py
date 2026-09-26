"""Immoware24 list imports over the API (/api/v1/imports/immoware24/lists).

The same logic as the operator commands ``python -m mhvp.imports.objektdaten`` and
``python -m mhvp.imports.kontakte`` (parse, prepare, apply_prepared), reachable from the CRM so
that no SSH access is needed. ``mode=preview`` runs everything inside a savepoint that is rolled
back; ``mode=apply`` writes and records an ``ImportRun`` (source ``immoware24:objektdaten`` or
``immoware24:kontakte``) whose items allow the usual undo (/imports/{id}/undo).
"""

import argparse
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from mhvp.ai.imports import Recorder
from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.contacts.models import ContactRoleCode
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import kontakte, objektdaten
from mhvp.imports.csvtext import decode_csv
from mhvp.imports.routers import WRITE, _need_domain

router = APIRouter(prefix="/imports/immoware24/lists", tags=["Import Immoware24"])
MAX_LIST_BYTES = 20 * 1024 * 1024
MODE = Query(default="preview", pattern="^(preview|apply)$")
LIST_ROLES: dict[str, ContactRoleCode] = {
    "eigentuemer": ContactRoleCode.EIGENTUEMER,
    "mieter": ContactRoleCode.MIETER,
    "bank": ContactRoleCode.BANK,
    "sonstige": ContactRoleCode.SONSTIGES,
}


async def _read_csv(file: UploadFile) -> tuple[str, str | None]:
    """Text of the upload and a note when it was not UTF-8 (Windows-1252 exports are read)."""
    data = await file.read()
    if not data:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"{file.filename or 'Die Datei'} ist leer."
        )
    if len(data) > MAX_LIST_BYTES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail=f"{file.filename or 'Die Datei'} ist zu groß."
        )
    text, note = decode_csv(data)
    return text, (f"{file.filename}: {note}" if note and file.filename else note)


async def _run(
    session: Any,
    principal: TenantPrincipal,
    *,
    mode: str,
    source: str,
    work: Any,
) -> dict[str, Any]:
    """Preview inside a rolled back savepoint; apply with an import run and its items."""
    if mode == "preview":
        nested = await session.begin_nested()
        try:
            report = await work(session, None)
        finally:
            await nested.rollback()
        return {"mode": "preview", "apply": False, **report}
    run_row = ImportRun(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        source=source,
        status=ImportStatus.APPLIED,
        document_ids=[],
    )
    session.add(run_row)
    await session.flush()
    report = await work(session, Recorder(session, run_row))
    run_row.summary = report["counts"]
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="import_run.applied",
        entity_type="import_run",
        entity_id=run_row.id,
        actor_user_id=principal.user_id,
        payload={"source": source, "counts": report["counts"]},
    )
    await session.flush()
    return {"mode": "apply", "apply": True, "import_run_id": str(run_row.id), **report}


@router.post(
    "/objektdaten", summary="Objekte und Einheiten aus der Objektliste (Testlauf oder Übernahme)"
)
async def import_objektdaten(
    request: Request,
    mode: str = MODE,
    file: UploadFile = File(),
    number_map: str = Form(default=""),
    skip_handed_over: bool = Form(default=False),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """``number_map``: ``ALT=NEU`` pairs separated by comma or line break for object numbers
    that are not three digits. Same rules as the command line (handbuch/import-objektdaten.md)."""
    _need_domain(principal)
    text, encoding_note = await _read_csv(file)
    try:
        mapping = objektdaten._parse_number_map(number_map.replace("\n", ",").split(","))
        parsed = objektdaten.parse_objektdaten(text, file.filename or None)
        prepared = objektdaten.prepare(parsed, mapping)
    except (argparse.ArgumentTypeError, ValueError) as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc) or "Datei unlesbar.") from exc
    file_notes = ([encoding_note] if encoding_note else []) + parsed.notes

    async def work(session: Any, recorder: Recorder | None) -> dict[str, Any]:
        return await objektdaten.apply_prepared(
            session,
            principal.tenant_id,
            principal.user_id,
            prepared,
            skip_handed_over=skip_handed_over,
            recorder=recorder,
            file_notes=file_notes,
        )

    async with tenant_tx(request, principal) as session:
        return await _run(session, principal, mode=mode, source="immoware24:objektdaten", work=work)


@router.post("/kontakte", summary="Kontakte aus den Kontaktlisten (Testlauf oder Übernahme)")
async def import_kontakte(
    request: Request,
    mode: str = MODE,
    files: list[UploadFile] = File(),
    roles: list[str] = Form(),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """One role (eigentuemer, mieter, bank, sonstige) per file, in the same order as ``files``."""
    _need_domain(principal)
    if len(files) != len(roles):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Je Datei ist genau eine Rolle anzugeben.")
    parsed = kontakte.ParsedKontakte()
    for upload, role_text in zip(files, roles, strict=True):
        role = LIST_ROLES.get(role_text.strip().lower())
        if role is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Rolle {role_text!r} unbekannt (eigentuemer, mieter, bank, sonstige).",
            )
        text, encoding_note = await _read_csv(upload)
        if encoding_note:
            parsed.notes.append(encoding_note)
        try:
            parsed.extend(kontakte.parse_kontakte(text, role, upload.filename or role_text))
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc) or "Datei unlesbar.") from exc
    prepared = kontakte.prepare(parsed)

    async def work(session: Any, recorder: Recorder | None) -> dict[str, Any]:
        return await kontakte.apply_prepared(
            session,
            principal.tenant_id,
            principal.user_id,
            prepared,
            recorder=recorder,
            file_notes=parsed.notes,
        )

    async with tenant_tx(request, principal) as session:
        return await _run(session, principal, mode=mode, source="immoware24:kontakte", work=work)
