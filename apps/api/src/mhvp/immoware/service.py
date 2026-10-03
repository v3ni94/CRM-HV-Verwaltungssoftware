"""Verbindungsaufbau und Lauf-Buchhaltung fuer die drei DAV-Arten (M32)."""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.config import get_settings
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import PinnedTarget, pin_target
from mhvp.documents.models import Document
from mhvp.immoware import caldav, carddav, webdav
from mhvp.immoware.client import (
    ReadOnlyDavClient,
    build_httpx_client,
    derive_caldav_url,
    derive_carddav_url,
    sanitize_error,
)
from mhvp.immoware.discovery import run_full_discovery
from mhvp.immoware.models import ImmowareConnection, ImmowareSyncRun, SyncKind, SyncStatus

log = logging.getLogger(__name__)

# Batchgroesse der Anwendungsphase: je Batch eine kurze Transaktion mit Commit, damit waehrend
# des DAV-Abrufs nie eine Transaktion offen bleibt (Produktionsbefund 27.09.2026: zwei Sessions
# "idle in transaction" ueber 17 bzw. 22 Minuten, CREATE INDEX CONCURRENTLY blockiert).
SYNC_BATCH_SIZE = 50
# Ein Lauf mit Status ``running``, der aelter ist, gilt als verwaist (Prozess beendet, ohne den
# Status zu setzen) und wird beim naechsten Start als ``failed`` abgeschlossen. Produktschutz,
# keine Rechtsgrundlage; Wert bewusst deutlich ueber der beobachteten Laufzeit (ca. 20 Minuten).
STALE_RUNNING_AFTER = timedelta(hours=2)


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
        ),
        pin=dav_pin,
    )


def dav_pin(url: str) -> PinnedTarget:
    """GAM-302: SSRF-Pruefung und Pinning je DAV-Anfrage (Plattformschalter wie Webhooks)."""
    return pin_target(url, allow_private=get_settings().webhook_allow_private_targets)


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


@dataclass
class SyncOutcome:
    seen: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    folder_errors: list[dict[str, object]] = field(default_factory=list)


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _lock_key(tenant_id: uuid.UUID, kind: SyncKind) -> str:
    return f"immoware_sync:{tenant_id}:{kind.value}"


async def start_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, kind: SyncKind
) -> ImmowareSyncRun:
    """Legt die Laufzeile an und verhindert Doppellaeufe je Tenant und Art: Pruefung und Anlage
    sind ueber ``pg_advisory_xact_lock`` serialisiert (Muster wie ``accounting.receivables``).
    Laeuft bereits ein Lauf gleicher Art (Status ``running``, juenger als
    ``STALE_RUNNING_AFTER``), wird ``IMW_SYNC_RUNNING`` (409) ausgeloest. Aeltere ``running``-Zeilen
    gelten als verwaist und werden als ``failed`` abgeschlossen. Der Aufrufer committet die
    Transaktion, bevor der DAV-Abruf beginnt."""
    now = datetime.now(UTC)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _lock_key(tenant_id, kind)}
    )
    running = await session.scalars(
        select(ImmowareSyncRun).where(
            ImmowareSyncRun.kind == kind, ImmowareSyncRun.status == SyncStatus.RUNNING
        )
    )
    for row in running:
        if now - row.started_at < STALE_RUNNING_AFTER:
            raise ProblemError(
                ErrorCodes.IMW_SYNC_RUNNING,
                detail=(
                    f"Die Abholung {kind.value} läuft seit "
                    f"{row.started_at.astimezone(UTC).strftime('%d.%m.%Y %H:%M')} UTC "
                    "und ist noch nicht abgeschlossen."
                ),
                extensions={"run_id": str(row.id)},
            )
        row.status = SyncStatus.FAILED
        row.error = (
            "Lauf ohne Abschluss (Prozess beendet); beim nächsten Start als abgebrochen markiert."
        )
        row.finished_at = now
    run = ImmowareSyncRun(tenant_id=tenant_id, kind=kind, started_at=now, status=SyncStatus.RUNNING)
    session.add(run)
    await session.flush()
    return run


async def _sync_webdav(
    client: ReadOnlyDavClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    base_url: str,
) -> SyncOutcome:
    fetched = await webdav.fetch_tree(client, base_url)  # HTTP, keine Transaktion offen
    outcome = SyncOutcome(seen=fetched.seen, folder_errors=fetched.folder_errors)
    now = datetime.now(UTC)
    for batch in _chunks(fetched.entries, SYNC_BATCH_SIZE):
        async with tenant_transaction(factory, tenant_id) as session:
            added, changed = await webdav.apply_entries(
                session, tenant_id=tenant_id, entries=batch, now=now
            )
        outcome.added += added
        outcome.changed += changed
    async with tenant_transaction(factory, tenant_id) as session:
        outcome.removed = await webdav.mark_stale(
            session, tenant_id=tenant_id, seen_hrefs={e.href for e in fetched.entries}, now=now
        )
    return outcome


async def _sync_carddav(
    client: ReadOnlyDavClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    carddav_url: str,
    *,
    auto_take_over: bool,
) -> SyncOutcome:
    remote = await carddav.fetch_hrefs(client, carddav_url)  # HTTP, keine Transaktion offen
    outcome = SyncOutcome(seen=len(remote))
    async with tenant_transaction(factory, tenant_id) as session:
        checksums = await carddav.load_checksums(session, tenant_id=tenant_id)
    now = datetime.now(UTC)
    for hrefs in _chunks(carddav.hrefs_to_fetch(remote, checksums), SYNC_BATCH_SIZE):
        cards = await carddav.fetch_cards(client, carddav_url, hrefs)  # HTTP je Batch
        async with tenant_transaction(factory, tenant_id) as session:
            added, changed = await carddav.apply_cards(
                session, tenant_id=tenant_id, cards=cards, etags=remote, now=now
            )
        outcome.added += added
        outcome.changed += changed
    async with tenant_transaction(factory, tenant_id) as session:
        outcome.removed = await carddav.mark_removed(
            session, tenant_id=tenant_id, remote_hrefs=set(remote), now=now
        )
    if auto_take_over:
        async with tenant_transaction(factory, tenant_id) as session:
            await take_over_contacts(session, tenant_id)
    return outcome


async def _sync_caldav(
    client: ReadOnlyDavClient,
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    caldav_url: str,
) -> SyncOutcome:
    remote = await caldav.fetch_events(client, caldav_url)  # HTTP, keine Transaktion offen
    outcome = SyncOutcome(seen=len(remote))
    now = datetime.now(UTC)
    for batch in _chunks(list(remote.items()), SYNC_BATCH_SIZE):
        async with tenant_transaction(factory, tenant_id) as session:
            added, changed = await caldav.apply_events(
                session, tenant_id=tenant_id, remote=dict(batch), now=now
            )
        outcome.added += added
        outcome.changed += changed
    async with tenant_transaction(factory, tenant_id) as session:
        outcome.removed = await caldav.mark_removed(
            session, tenant_id=tenant_id, remote_hrefs=set(remote), now=now
        )
    return outcome


async def _load_run(session: AsyncSession, run_id: uuid.UUID) -> ImmowareSyncRun:
    run = await session.get(ImmowareSyncRun, run_id)
    if run is None:
        raise RuntimeError(f"immoware_sync_run {run_id} not found")
    return run


async def run_sync(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, kind: SyncKind
) -> ImmowareSyncRun:
    """Fuehrt eine Abholung aus, ohne waehrend der HTTP-Aufrufe eine Transaktion offen zu halten
    (Produktionsbefund 27.09.2026). Ablauf mit je eigener, kurzer Transaktion (RLS: die
    Mandantenvariable wird ueber ``tenant_transaction`` in jeder Transaktion neu gesetzt):

    1. Verbindung laden, Doppellauf pruefen, Laufzeile ``running`` anlegen, Commit (sichtbar).
    2. DAV-Abruf ohne Session; Anwendung der Ergebnisse in Batches zu ``SYNC_BATCH_SIZE`` mit
       Commit je Batch.
    3. Laufzeile mit Zaehlern und Status ``ok`` abschliessen, Commit. Im Fehlerfall wird die
       Laufzeile in eigener Transaktion auf ``failed`` gesetzt und committet.

    Ein zweiter Start bei laufendem Lauf gleicher Art loest ``IMW_SYNC_RUNNING`` (409) aus."""
    async with tenant_transaction(factory, tenant_id) as session:
        connection = await require_connection(session)
        run = await start_run(session, tenant_id=tenant_id, kind=kind)
        run_id = run.id
        client = dav_client(connection)
        base_url = connection.base_url or ""
        card_url = carddav_url(connection)
        cal_url = caldav_url(connection)
        auto_take_over = bool(connection.auto_take_over_contacts)
    try:
        if kind is SyncKind.WEBDAV:
            outcome = await _sync_webdav(client, factory, tenant_id, base_url)
        elif kind is SyncKind.CARDDAV:
            outcome = await _sync_carddav(
                client, factory, tenant_id, card_url, auto_take_over=auto_take_over
            )
        else:
            outcome = await _sync_caldav(client, factory, tenant_id, cal_url)
    except Exception as exc:
        error = sanitize_error(str(exc))
        log.warning(
            "immoware sync failed",
            extra={"tenant_id": str(tenant_id), "kind": kind.value, "run_id": str(run_id)},
        )
        async with tenant_transaction(factory, tenant_id) as session:
            run = await _load_run(session, run_id)
            run.status = SyncStatus.FAILED
            run.error = error
            run.finished_at = datetime.now(UTC)
        return run
    finally:
        await client.aclose()
    async with tenant_transaction(factory, tenant_id) as session:
        run = await _load_run(session, run_id)
        run.seen, run.added, run.changed, run.removed = (
            outcome.seen,
            outcome.added,
            outcome.changed,
            outcome.removed,
        )
        if outcome.folder_errors:
            run.folder_errors = outcome.folder_errors
        run.status = SyncStatus.OK
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
    from mhvp.contacts.models import (
        Contact,
        ContactEmail,
        ContactKind,
        ContactPhone,
        PhoneLabel,
    )
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
        for email in dict.fromkeys(e.strip() for e in row.emails if e and e.strip()):
            if len(email) > 320:
                continue
            session.add(ContactEmail(tenant_id=tenant_id, contact_id=contact.id, email=email))
        for phone in dict.fromkeys(p.strip() for p in row.phones if p and p.strip()):
            # ``contact_phone.label`` ist Pflicht (NOT NULL, Betreibermeldung 26.09.2026);
            # vCard-Typen liegen im Spiegel nicht vor, daher "other". Nummern ueber 32 Zeichen
            # passen nicht in die Spalte und werden ausgelassen statt den Lauf abzubrechen.
            if len(phone) > 32:
                continue
            session.add(
                ContactPhone(
                    tenant_id=tenant_id,
                    contact_id=contact.id,
                    label=PhoneLabel.OTHER,
                    number=phone,
                )
            )
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
