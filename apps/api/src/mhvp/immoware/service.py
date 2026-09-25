"""Verbindungsaufbau und Lauf-Buchhaltung fuer die drei DAV-Arten (M32)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.immoware.caldav import CalDavPullResult, pull_events
from mhvp.immoware.carddav import CardDavPullResult, pull_contacts
from mhvp.immoware.client import (
    ReadOnlyDavClient,
    build_httpx_client,
    derive_caldav_url,
    derive_carddav_url,
    sanitize_error,
)
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
    return connection.carddav_url or derive_carddav_url(connection.base_url or "")


def caldav_url(connection: ImmowareConnection) -> str:
    return connection.caldav_url or derive_caldav_url(connection.base_url or "")


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
        connection.last_error = None if connection.last_check_ok else sanitize_error(
            f"HTTP {response.status_code}"
        )
    except Exception as exc:
        connection.last_check_ok = False
        connection.last_error = sanitize_error(str(exc))
    finally:
        await client.aclose()
    connection.last_check_at = datetime.now(UTC)
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
        run.status = SyncStatus.OK
    except Exception as exc:
        run.status = SyncStatus.FAILED
        run.error = sanitize_error(str(exc))
    finally:
        await client.aclose()
        run.finished_at = datetime.now(UTC)
    return run
