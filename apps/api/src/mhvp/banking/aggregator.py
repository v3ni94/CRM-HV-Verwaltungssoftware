"""Orchestration of the read-only finAPI stage (M31): connect -> select and assign accounts ->
fetch on explicit user action -> verify server side -> import without loss or duplicates.

No scheduled bank fetches: every run starts with a user click; background jobs only finish the
requested run. A browser redirect is never taken as proof - results are re-checked against the
provider with our own credentials before any state changes (docs/BANKING-FINAPI.md)."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import services
from mhvp.banking.camt import RawTransaction
from mhvp.banking.finapi import (
    AggregatorError,
    BankingAggregator,
    ProviderAccount,
    ProviderTransaction,
    user_credentials,
)
from mhvp.banking.models import (
    AccountUsage,
    BankAccountLink,
    BankBalance,
    BankConnection,
    BankSyncRun,
    ConnectionStatus,
    Connector,
    FetchStatus,
)
from mhvp.core import crypto
from mhvp.core.config import Settings
from mhvp.core.problems import ErrorCodes, ProblemError

ClientFactory = Callable[[BankConnection], BankingAggregator]

ACTIVE_FETCH: tuple[FetchStatus, ...] = (
    FetchStatus.QUEUED,
    FetchStatus.RUNNING,
    FetchStatus.AWAITING_AUTHORIZATION,
    FetchStatus.IMPORTING,
)
_WEBFORM_DONE = ("COMPLETED",)
_WEBFORM_GONE = ("ABORTED", "EXPIRED", "NOT_YET_OPENED_EXPIRED")
_TASK_DONE = ("COMPLETED", "COMPLETED_WITH_ERROR")


def callback_url(
    settings: Settings, tenant_id: uuid.UUID, run_id: uuid.UUID, token: str
) -> str | None:
    base = (settings.banking_finapi_callback_base_url or "").rstrip("/")
    if not base:
        return None
    return f"{base}/api/v1/banking/finapi/callback/{tenant_id}/{run_id}?token={token}"


def _now() -> datetime:
    return datetime.now(UTC)


async def start_import(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    bank_name: str,
    authorization_context: str,
    client_factory: ClientFactory,
) -> tuple[BankConnection, BankSyncRun]:
    """Creates the connection attempt and the provider web form. Bank choice, login and TAN
    happen only inside the provider form; we never see a bank PIN."""
    connection = BankConnection(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        connector=Connector.AGGREGATOR_FINAPI,
        bank_name=bank_name[:200] or "Bankverbindung (finAPI)",
        status=ConnectionStatus.NOT_CONFIGURED,
        authorized_user_id=actor_user_id,
        authorization_context=authorization_context,
    )
    session.add(connection)
    await session.flush()
    client = client_factory(connection)
    try:
        credentials = await client.ensure_user()
        connection.credentials = json.dumps(credentials)
        token = uuid.uuid4().hex
        run = BankSyncRun(
            tenant_id=tenant_id,
            created_by=actor_user_id,
            connection_id=connection.id,
            source="finapi",
            status="running",
            trigger="initial_import",
            actor_user_id=actor_user_id,
            fetch_status=FetchStatus.AWAITING_AUTHORIZATION,
        )
        session.add(run)
        await session.flush()
        webform = await client.create_import_webform(
            callback_url(settings, tenant_id, run.id, token)
        )
    finally:
        await client.aclose()
    run.webform_id, run.webform_url = webform.id, webform.url
    connection.provider_refs = {
        **connection.provider_refs,
        "webform_id": webform.id,
        "callback_token": token,
    }
    await session.flush()
    return connection, run


async def confirm_import(
    session: AsyncSession,
    connection: BankConnection,
    run: BankSyncRun,
    client: BankingAggregator,
) -> dict[str, Any]:
    """Server-side verification after the web form: a redirect or callback is only a hint."""
    if not run.webform_id:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein WebForm für diesen Lauf.")
    webform = await client.get_webform(run.webform_id)
    if webform.status in _WEBFORM_GONE:
        run.fetch_status = (
            FetchStatus.EXPIRED if "EXPIRED" in webform.status else FetchStatus.CANCELED
        )
        run.status, run.finished_at = "done", _now()
        run.errors = [*run.errors, f"WebForm {webform.status}"]
        # Abbruch oder Ablauf zerstoert keine Kontoverknuepfung; die Verbindung bleibt.
        return {"status": run.fetch_status.value, "accounts": 0}
    if webform.status not in _WEBFORM_DONE or not webform.bank_connection_id:
        return {"status": "pending", "accounts": 0}
    connection.provider_refs = {
        **connection.provider_refs,
        "bank_connection_id": webform.bank_connection_id,
    }
    connection.status = ConnectionStatus.ACTIVE
    connection.error_message = None
    accounts = await client.list_accounts(webform.bank_connection_id)
    links = await sync_account_links(session, connection, accounts)
    run.fetch_status = FetchStatus.SUCCEEDED
    run.status, run.finished_at = "done", _now()
    run.counts = {**run.counts, "accounts": len(links)}
    await session.flush()
    return {"status": "succeeded", "accounts": len(links)}


async def sync_account_links(
    session: AsyncSession, connection: BankConnection, accounts: list[ProviderAccount]
) -> list[BankAccountLink]:
    """Controlled source mapping: an existing link is found by provider id, otherwise by IBAN
    fingerprint within the same connection (an IBAN match is a hint, never a cross-tenant or
    cross-connection merge). New external references never create internal accounts."""
    existing = (
        await session.scalars(
            select(BankAccountLink).where(BankAccountLink.connection_id == connection.id)
        )
    ).all()
    by_provider = {link.provider_account_id: link for link in existing}
    by_iban = {link.iban_fingerprint: link for link in existing if link.iban_fingerprint}
    result: list[BankAccountLink] = []
    for account in accounts:
        fingerprint = crypto.fingerprint(account.iban) if account.iban else None
        link = by_provider.get(account.id)
        if link is None and fingerprint and fingerprint in by_iban:
            # Wiederanbindung mit geaenderten externen IDs: Quellenzuordnung kontrolliert
            # aktualisieren, Historie und interne Verknuepfung bleiben erhalten.
            link = by_iban[fingerprint]
            link.provider_account_id = account.id
        if link is None:
            link = BankAccountLink(
                tenant_id=connection.tenant_id,
                connection_id=connection.id,
                provider_account_id=account.id,
                currency=account.currency,
                usage=AccountUsage.CURRENT,
            )
            session.add(link)
        link.holder_name = account.holder_name
        link.iban = account.iban
        link.iban_fingerprint = fingerprint
        link.label = account.label
        link.account_type = account.account_type
        link.currency = account.currency
        await session.flush()
        _snapshot_balance(session, link, account)
        result.append(link)
    return result


def _snapshot_balance(
    session: AsyncSession, link: BankAccountLink, account: ProviderAccount
) -> None:
    reference_at = None
    if account.balance_date:
        try:
            reference_at = datetime.fromisoformat(account.balance_date.replace("Z", "+00:00"))
        except ValueError:
            reference_at = None  # kein verlaesslicher bankseitiger Zeitpunkt: leer lassen
    session.add(
        BankBalance(
            tenant_id=link.tenant_id,
            account_link_id=link.id,
            balance=Decimal(account.balance) if account.balance is not None else None,
            available=Decimal(account.available) if account.available is not None else None,
            currency=account.currency,
            balance_type="booked",
            bank_reference_at=reference_at,
        )
    )


async def active_run(session: AsyncSession, connection_id: uuid.UUID) -> BankSyncRun | None:
    run: BankSyncRun | None = await session.scalar(
        select(BankSyncRun)
        .where(
            BankSyncRun.connection_id == connection_id,
            BankSyncRun.fetch_status.in_(ACTIVE_FETCH),
        )
        .order_by(BankSyncRun.created_at.desc())
        .limit(1)
    )
    return run


async def start_fetch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    connection: BankConnection,
    trigger: str = "manual",
) -> tuple[BankSyncRun, bool]:
    """Creates the fetch run; double clicks, second tabs and parallel colleagues get the same
    active run back instead of a second provider process. Returns (run, created)."""
    running = await active_run(session, connection.id)
    if running is not None:
        return running, False
    run = BankSyncRun(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        connection_id=connection.id,
        source="finapi",
        status="running",
        trigger=trigger,
        actor_user_id=actor_user_id,
        fetch_status=FetchStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    return run, True


async def run_fetch(
    session: AsyncSession,
    settings: Settings,
    run: BankSyncRun,
    connection: BankConnection,
    client: BankingAggregator,
    *,
    poll: Callable[[], Any] | None = None,
    max_polls: int = 60,
) -> None:
    """One provider update per connection: start the documented background update, follow the
    task, switch to the web form when the task demands one, then import per account."""
    bank_connection_id = str(connection.provider_refs.get("bank_connection_id") or "")
    if not bank_connection_id:
        _fail(run, connection, "Verbindung hat keine Provider-Referenz (Import unvollständig).")
        return
    run.fetch_status = FetchStatus.RUNNING
    await session.flush()
    try:
        task = await client.start_update(bank_connection_id)
        run.provider_task_id = task.id
        polls = 0
        while task.status not in _TASK_DONE:
            if task.status == "WEB_FORM_REQUIRED":
                # Ab hier zaehlt das WebForm, nicht der alte Task (Q8): Freigabe anfordern,
                # Lauf sichtbar parken; nach der Freigabe wird derselbe Lauf fortgesetzt.
                token = str(connection.provider_refs.get("callback_token") or uuid.uuid4().hex)
                connection.provider_refs = {**connection.provider_refs, "callback_token": token}
                webform = await client.create_update_webform(
                    bank_connection_id,
                    callback_url(settings, connection.tenant_id, run.id, token),
                )
                run.webform_id, run.webform_url = webform.id, webform.url
                run.fetch_status = FetchStatus.AWAITING_AUTHORIZATION
                await session.flush()
                return
            polls += 1
            if polls > max_polls:
                _fail(
                    run,
                    connection,
                    "Zeitüberschreitung beim Provider-Update; Status später erneut prüfen "
                    "(kein neuer Vorgang nötig).",
                )
                return
            if poll is not None:
                await poll()
            task = await client.get_task(task.id)
        task_errors = list(task.errors)
        if task.status == "COMPLETED_WITH_ERROR":
            task_errors.append("Provider meldet Abschluss mit Fehlern.")
        await import_accounts(
            session, settings, run, connection, client, provider_errors=task_errors
        )
    except AggregatorError as exc:
        _fail(run, connection, str(exc))


async def resume_after_webform(
    session: AsyncSession,
    settings: Settings,
    run: BankSyncRun,
    connection: BankConnection,
    client: BankingAggregator,
) -> None:
    """After the renewed bank authorization the SAME run continues; nothing is re-created.
    The web form result is verified server side before any import."""
    if run.fetch_status is not FetchStatus.AWAITING_AUTHORIZATION or not run.webform_id:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Dieser Lauf wartet auf keine Freigabe.")
    webform = await client.get_webform(run.webform_id)
    if webform.status in _WEBFORM_GONE:
        run.fetch_status = (
            FetchStatus.EXPIRED if "EXPIRED" in webform.status else FetchStatus.CANCELED
        )
        run.status, run.finished_at = "done", _now()
        run.errors = [*run.errors, f"WebForm {webform.status}"]
        return
    if webform.status not in _WEBFORM_DONE:
        return  # noch offen: Zustand unveraendert lassen
    await import_accounts(session, settings, run, connection, client, provider_errors=[])


async def import_accounts(
    session: AsyncSession,
    settings: Settings,
    run: BankSyncRun,
    connection: BankConnection,
    client: BankingAggregator,
    *,
    provider_errors: list[str],
) -> None:
    """Per-account import of booked transactions with overlap window and idempotent ingest.
    READY alone is no success: every selected account gets its own result; a failing account
    never blocks the others (partial)."""
    run.fetch_status = FetchStatus.IMPORTING
    await session.flush()
    bank_connection_id = str(connection.provider_refs.get("bank_connection_id") or "")
    accounts = {a.id: a for a in await client.list_accounts(bank_connection_id)}
    await sync_account_links(session, connection, list(accounts.values()))
    links = (
        await session.scalars(
            select(BankAccountLink).where(
                BankAccountLink.connection_id == connection.id,
                BankAccountLink.is_selected.is_(True),
            )
        )
    ).all()
    results: dict[str, Any] = {}
    counts = {"new": 0, "duplicates": 0, "possible_duplicates": 0, "pending_skipped": 0}
    failures = 0
    now = _now()
    for link in links:
        link.last_attempt_at = now
        key = str(link.id)
        if link.property_bank_account_id is None:
            # Unzugeordnete Konten gelangen nicht in die Buchhaltung.
            results[key] = {"status": "skipped", "reason": "kein internes Konto zugeordnet"}
            continue
        if link.provider_account_id not in accounts:
            failures += 1
            link.last_error = "Konto wird von der Bank nicht mehr geliefert."
            results[key] = {"status": "failed", "reason": link.last_error}
            continue
        try:
            since = None
            if link.last_imported_at is not None:
                overlap = timedelta(days=settings.banking_fetch_overlap_days)
                since = (link.last_imported_at - overlap).date().isoformat()
            rows = await client.list_transactions(link.provider_account_id, since)
        except AggregatorError as exc:
            failures += 1
            link.last_error = str(exc)[:500]
            results[key] = {"status": "failed", "reason": link.last_error}
            continue  # ein fehlerhaftes Konto blockiert die anderen nicht
        booked = [t for t in rows if not t.is_pending]
        pending = len(rows) - len(booked)
        from mhvp.properties.models import PropertyBankAccount

        account = await session.get(PropertyBankAccount, link.property_bank_account_id)
        ingest = await services.ingest_transactions(
            session,
            tenant_id=connection.tenant_id,
            account=account,
            statement_id=None,
            sync_run_id=run.id,
            transactions=[_raw_transaction(t) for t in booked],
        )
        for name in ("new", "duplicates", "possible_duplicates"):
            counts[name] += ingest[name]
        counts["pending_skipped"] += pending
        link.last_bank_success_at = now
        link.last_imported_at = now
        link.last_error = None
        results[key] = {"status": "ok", **ingest, "pending_skipped": pending}
    run.account_results = results
    run.counts = {**run.counts, **counts}
    run.errors = [*run.errors, *provider_errors]
    if failures and failures == sum(1 for r in results.values() if r["status"] != "skipped"):
        run.fetch_status = FetchStatus.FAILED
    elif failures or provider_errors:
        run.fetch_status = FetchStatus.PARTIAL
    else:
        run.fetch_status = FetchStatus.SUCCEEDED
    run.status, run.finished_at = "done", _now()
    connection.last_sync_at = now
    connection.error_message = "; ".join(provider_errors)[:500] or None
    await session.flush()


async def disconnect(
    session: AsyncSession, connection: BankConnection, client: BankingAggregator
) -> str | None:
    """First block further use, then remove the provider connection in the available scope.
    Local accounts, transactions and runs stay (retention); we never claim a bank-side consent
    revocation - only the provider connection is deleted."""
    connection.status = ConnectionStatus.DISABLED
    await session.flush()
    bank_connection_id = str(connection.provider_refs.get("bank_connection_id") or "")
    external_error: str | None = None
    if bank_connection_id:
        try:
            await client.delete_bank_connection(bank_connection_id)
        except AggregatorError as exc:
            external_error = str(exc)[:500]
            connection.error_message = external_error
    return external_error


def _fail(run: BankSyncRun, connection: BankConnection, message: str) -> None:
    run.fetch_status = FetchStatus.FAILED
    run.status = "done"
    run.finished_at = _now()
    run.errors = [*run.errors, message]
    connection.error_message = message[:500]


def _raw_transaction(tx: ProviderTransaction) -> RawTransaction:
    from datetime import date

    return RawTransaction(
        # Dokumentierte, stabile Umsatz-ID des Providers; Gueltigkeitsbereich ist das Konto.
        bank_reference=f"finapi:{tx.id}",
        booking_date=date.fromisoformat(tx.booking_date[:10]),
        value_date=date.fromisoformat(tx.value_date[:10]) if tx.value_date else None,
        amount=Decimal(tx.amount),
        currency=tx.currency,
        counterpart_name=tx.counterpart_name,
        counterpart_iban=tx.counterpart_iban,
        counterpart_bic=tx.counterpart_bic,
        purpose=tx.purpose,
        end_to_end_id=tx.end_to_end_id,
        mandate_reference=tx.mandate_reference,
        creditor_id=tx.creditor_id,
        transaction_code=None,
        raw=tx.raw,
    )


def client_credentials(connection: BankConnection) -> dict[str, str] | None:
    return user_credentials(connection.credentials)
