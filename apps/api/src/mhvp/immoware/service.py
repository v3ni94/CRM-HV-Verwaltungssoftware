"""Verbindungsaufbau und Lauf-Buchhaltung fuer die drei DAV-Arten (M32)."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.immoware.caldav import CalDavPullResult, pull_events
from mhvp.immoware.carddav import CardDavPullResult, pull_contacts
from mhvp.immoware.client import (
    ReadOnlyDavClient,
    build_httpx_client,
    derive_caldav_url,
    derive_carddav_url,
    sanitize_error,
)
from mhvp.immoware.discovery import run_full_discovery
from mhvp.immoware.models import ImmowareConnection, ImmowareSyncRun, SyncKind, SyncStatus
from mhvp.immoware.webdav import WebdavPullResult, pull_tree


async def get_connection(session: AsyncSession) -> ImmowareConnection | None:
    return await session.scalar(select(ImmowareConnection))


async def require_connection(session: AsyncSession) -> ImmowareConnection:
    connection = await get_connection(session)
    if (
        connection is None
        or not connection.enabled
        or not connection.base_url
        or not connection.username
    ):
        raise ProblemError(ErrorCodes.IMW_NOT_CONFIGURED)
    return connection


def dav_client(connection: ImmowareConnection) -> ReadOnlyDavClient:
    return ReadOnlyDavClient(
        build_httpx_client(
            username=connection.username,
            password=connection.password,
            verify_tls=connection.verify_tls,
        )
    )


def carddav_url(connection: ImmowareConnection) -> str:
    return connection.carddav_url or derive_carddav_url(
        connection.base_url or "", connection.username
    )


def caldav_url(connection: ImmowareConnection) -> str:
    return connection.caldav_url or derive_caldav_url(
        connection.base_url or "", connection.username
    )


async def check_connection(
    session: AsyncSession, connection: ImmowareConnection
) -> ImmowareConnection:
    """PROPFIND Depth 0 auf base_url, Ergebnis in der Connection gespeichert."""
    client = dav_client(connection)
    try:
        response = await client.request(
            "PROPFIND",
            connection.base_url or "",
            content=(
                b'<?xml version="1.0" encoding="utf-8" ?>'
                b'<D:propfind xmlns:D="DAV:"><D:prop><D:resourcetype/></D:prop></D:propfind>'
            ),
            headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
        )
        connection.last_check_ok = response.status_code < 400
        connection.last_error = (
            None if connection.last_check_ok else sanitize_error(f"HTTP {response.status_code}")
        )
    except Exception as exc:
        connection.last_check_ok = False
        connection.last_error = sanitize_error(str(exc))
    finally:
        await client.aclose()
    connection.last_check_at = datetime.now(UTC)
    return connection


async def diagnose_connection(
    session: AsyncSession, connection: ImmowareConnection
) -> ImmowareConnection:
    """RFC-6764/4918-Discovery auf Basis von ``base_url``; speichert Ergebnis und Schritte
    (Betreiberbericht 25.09.2026). Manuell gesetzte URLs werden nie ueberschrieben."""
    if not connection.base_url:
        raise ProblemError(ErrorCodes.IMW_NOT_CONFIGURED)
    client = dav_client(connection)
    try:
        discovery = await run_full_discovery(client, connection.base_url, connection.username)
    finally:
        await client.aclose()

    if discovery.carddav_url and not connection.carddav_url:
        connection.carddav_url = discovery.carddav_url
        connection.carddav_url_discovered = True
    if discovery.caldav_url and not connection.caldav_url:
        connection.caldav_url = discovery.caldav_url
        connection.caldav_url_discovered = True
    if discovery.webdav_url and not connection.webdav_root_url:
        connection.webdav_root_url = discovery.webdav_url
        connection.webdav_root_discovered = True

    all_404 = bool(discovery.steps) and all(
        step.status == 404 for step in discovery.steps if step.status is not None
    )
    connection.last_diagnosis = {
        "steps": [asdict(step) for step in discovery.steps],
        "carddav_url": discovery.carddav_url,
        "caldav_url": discovery.caldav_url,
        "webdav_url": discovery.webdav_url,
        "dav_module_likely_not_booked": all_404,
    }
    connection.last_diagnosis_at = datetime.now(UTC)
    return connection


async def run_sync(
    session: AsyncSession, connection: ImmowareConnection, kind: SyncKind
) -> ImmowareSyncRun:
    run = ImmowareSyncRun(
        tenant_id=connection.tenant_id,
        kind=kind,
        started_at=datetime.now(UTC),
        status=SyncStatus.RUNNING,
    )
    session.add(run)
    await session.flush()
    client = dav_client(connection)
    outcome: WebdavPullResult | CardDavPullResult | CalDavPullResult
    try:
        if kind is SyncKind.WEBDAV:
            outcome = await pull_tree(
                client, session, tenant_id=connection.tenant_id, base_url=connection.base_url or ""
            )
        elif kind is SyncKind.CARDDAV:
            outcome = await pull_contacts(
                client, session, tenant_id=connection.tenant_id, carddav_url=carddav_url(connection)
            )
            if connection.auto_take_over_contacts:
                await take_over_contacts(session, connection.tenant_id)
        else:
            outcome = await pull_events(
                client, session, tenant_id=connection.tenant_id, caldav_url=caldav_url(connection)
            )
        run.seen, run.added, run.changed, run.removed = (
            outcome.seen,
            outcome.added,
            outcome.changed,
            outcome.removed,
        )
        if isinstance(outcome, WebdavPullResult) and outcome.folder_errors:
            run.folder_errors = outcome.folder_errors
        run.status = SyncStatus.OK
    except Exception as exc:
        run.status = SyncStatus.FAILED
        run.error = sanitize_error(str(exc))
    finally:
        await client.aclose()
        run.finished_at = datetime.now(UTC)
    return run


async def take_over_contacts(
    session: AsyncSession,
    tenant_id: object,
    *,
    contact_ids: list[Any] | None = None,
) -> dict[str, int]:
    """Bulk-Uebernahme unverknuepfter ``immoware_dav_contact``-Zeilen als CRM-Kontakte
    (Betreiberbericht 25.09.2026): Duplikatpruefung ueber ``contact_services.find_duplicates``;
    bereits verknuepfte oder als Duplikat erkannte Zeilen werden uebersprungen (idempotent)."""
    from mhvp.contacts import schemas as contact_schemas
    from mhvp.contacts import services as contact_services
    from mhvp.contacts.models import Contact, ContactEmail, ContactKind, ContactPhone
    from mhvp.immoware.models import ImmowareDavContact

    stmt = select(ImmowareDavContact).where(
        ImmowareDavContact.tenant_id == tenant_id,
        ImmowareDavContact.deleted_at.is_(None),
        ImmowareDavContact.matched_contact_id.is_(None),
    )
    if contact_ids:
        stmt = stmt.where(ImmowareDavContact.id.in_(contact_ids))
    rows = list(await session.scalars(stmt))

    created = 0
    linked = 0
    skipped = 0
    for row in rows:
        probe = contact_schemas.DuplicateQuery(
            first_name=(row.fn or "").split(" ")[0] or None,
            last_name=" ".join((row.fn or "").split(" ")[1:]) or None,
            company_name=row.org,
            email=row.emails[0] if row.emails else None,
            phone=row.phones[0] if row.phones else None,
        )
        duplicates = await contact_services.find_duplicates(session, probe)
        strong = [d for d in duplicates if d[1] >= 0.9]
        if strong:
            row.matched_contact_id = strong[0][0].id
            linked += 1
            continue
        if not row.fn and not row.org:
            skipped += 1
            continue
        kind = ContactKind.COMPANY if row.org and not row.fn else ContactKind.PERSON
        display_name = row.fn or row.org or row.href
        contact = Contact(
            tenant_id=tenant_id,
            kind=kind,
            company_name=row.org if kind is ContactKind.COMPANY else None,
            first_name=(
                None if kind is ContactKind.COMPANY else (row.fn or "").split(" ")[0] or None
            ),
            last_name=None
            if kind is ContactKind.COMPANY
            else " ".join((row.fn or "").split(" ")[1:]) or row.fn,
            display_name=display_name,
            external_ids={"immoware24_carddav_href": row.href},
        )
        session.add(contact)
        await session.flush()
        for email in row.emails:
            session.add(ContactEmail(tenant_id=tenant_id, contact_id=contact.id, email=email))
        for phone in row.phones:
            session.add(ContactPhone(tenant_id=tenant_id, contact_id=contact.id, number=phone))
        row.matched_contact_id = contact.id
        created += 1
    await session.flush()
    return {"created": created, "linked": linked, "skipped": skipped, "total": len(rows)}


async def take_over_document(
    session: AsyncSession,
    blobs: Any,
    connection: ImmowareConnection,
    row: Any,
    *,
    created_by: uuid.UUID | None,
) -> tuple[Any, bool]:
    """Uebernimmt eine einzelne ``immoware_dav_document``-Zeile als CRM-Dokument (GET per
    ``ReadOnlyDavClient``, Speicherung ueber ``documents.services.store_document``); idempotent
    je href+etag (Betreiberbericht 25.09.2026). Rueckgabe ``(document, created)``; ``created`` ist
    ``False``, wenn die Zeile bereits mit demselben etag uebernommen war."""
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import store_document
    from mhvp.immoware.webdav import download
    from mhvp.properties.models import Property

    if row.taken_over_document_id is not None and row.taken_over_etag == row.etag:
        existing = await session.get(Document, row.taken_over_document_id)
        if existing is not None:
            return existing, False

    href = row.href
    base = (connection.base_url or "").rstrip("/")
    url = href if href.startswith("http") else base + "/" + href.lstrip("/")
    client = dav_client(connection)
    try:
        chunks = [chunk async for chunk in download(client, url)]
    finally:
        await client.aclose()
    data = b"".join(chunks)
    mime_type = row.content_type or "application/octet-stream"
    filename = row.display_name or href.rsplit("/", 1)[-1] or "dokument"

    links: list[tuple[str, uuid.UUID, LinkRole]] = []
    if row.object_number_guess:
        prop = await session.scalar(
            select(Property).where(
                Property.tenant_id == connection.tenant_id,
                Property.number == row.object_number_guess,
            )
        )
        if prop is not None:
            links.append(("property", prop.id, LinkRole.ORIGINAL))

    document = await store_document(
        session,
        blobs,
        tenant_id=connection.tenant_id,
        data=data,
        title=filename,
        filename=filename,
        mime_type=mime_type,
        source=DocumentSource.IMPORT,
        category_id=None,
        links=links,
        created_by=created_by,
    )
    row.taken_over_document_id = document.id
    row.taken_over_etag = row.etag
    await session.flush()
    return document, True


async def take_over_documents_in_folder(
    session: AsyncSession,
    blobs: Any,
    connection: ImmowareConnection,
    *,
    folder_prefix: str,
    created_by: uuid.UUID | None,
) -> dict[str, int]:
    """Bulk-Uebernahme aller Dateien (keine Sammlungen) unterhalb eines Ordnerpfads
    (Betreiberbericht 25.09.2026, Auftragspunkt 4). Fehler bei einzelnen Dateien brechen den
    Lauf nicht ab (rule 0.1.9: konkurrenz-/fehlerrobust), sondern werden gezaehlt."""
    from mhvp.immoware.models import ImmowareDavDocument

    rows = list(
        await session.scalars(
            select(ImmowareDavDocument).where(
                ImmowareDavDocument.tenant_id == connection.tenant_id,
                ImmowareDavDocument.deleted_at.is_(None),
                ImmowareDavDocument.is_collection.is_(False),
                ImmowareDavDocument.href.like(f"{folder_prefix}%"),
            )
        )
    )
    created = 0
    linked = 0
    failed = 0
    for row in rows:
        try:
            _, was_created = await take_over_document(
                session, blobs, connection, row, created_by=created_by
            )
        except Exception:
            failed += 1
            continue
        if was_created:
            created += 1
        else:
            linked += 1
    return {"created": created, "linked": linked, "failed": failed, "total": len(rows)}
