"""FinTS/HBCI PIN/TAN endpoints (/api/v1/banking/fints, M11-01 addendum 27.09.2026).

Flow (docs/integrations/fints.md): institute search, create connection (login and PIN are
stored encrypted, a worker step is queued), poll the session (status, challenge), hand in
the TAN or poll the decoupled confirmation, assign the reported accounts to internal bank
accounts, refresh balances and transactions on click (new session, TAN again when the bank
requires it, PSD2 90 days), disconnect. Read only: no payment initiation (G2 stays closed).
Login, PIN and TAN are never returned and never logged.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select

from mhvp.banking import fints as fints_mod
from mhvp.banking.models import (
    BankConnection,
    BankSyncRun,
    ConnectionStatus,
    Connector,
    FinTsAccountLink,
    FinTsConnection,
    FinTsSession,
    FinTsSessionStatus,
)
from mhvp.contacts.validation import normalise_iban
from mhvp.core import crypto
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import BankAccountKind, LegalEntity, Property, PropertyBankAccount
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/banking/fints", tags=["Bank"])

READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
BANKING_APPROVE = require_permission("banking:approve")

OPEN_STATES = (
    FinTsSessionStatus.QUEUED,
    FinTsSessionStatus.RUNNING,
    FinTsSessionStatus.AWAITING_TAN,
    FinTsSessionStatus.AWAITING_DECOUPLED,
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinTsConfigOut(BaseModel):
    """Whether the FinTS product registration (``MHVP_FINTS_PRODUCT_ID``) is set. Without it
    the UI shows the hint of ``MHVP-BANK-0007`` instead of the connect button."""

    configured: bool


class InstituteOut(BaseModel):
    blz: str
    name: str
    city: str
    bic: str | None
    fints_url: str | None
    connectable: bool


class FinTsConnectionIn(_In):
    """Bank access data. `institute` is a BLZ, BIC or IBAN; the institute list resolves it.
    The PIN is write only: stored encrypted, never returned."""

    institute: str = Field(min_length=5, max_length=40)
    login: str = Field(min_length=1, max_length=64)
    pin: str = Field(min_length=1, max_length=64)
    tan_mechanism: str | None = Field(default=None, max_length=3)
    bank_name: str | None = Field(default=None, max_length=200)


class RestartIn(_In):
    """New connect session for an existing connection: after a rejected PIN (fresh PIN
    required), to switch the TAN mechanism, or when the bank asks for a new SCA."""

    pin: str | None = Field(default=None, min_length=1, max_length=64)
    tan_mechanism: str | None = Field(default=None, max_length=3)


class TanIn(_In):
    """TAN for `awaiting_tan`; omitted for a decoupled poll (`awaiting_decoupled`)."""

    tan: str | None = Field(default=None, min_length=1, max_length=64)


class RefreshIn(_In):
    since: date | None = None
    until: date | None = None


class AssignIn(_In):
    """Either an existing internal account (its IBAN must match) or a new one created for
    the property and legal entity from the bank's IBAN."""

    property_bank_account_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    legal_entity_id: uuid.UUID | None = None
    kind: BankAccountKind | None = None
    holder: str | None = Field(default=None, min_length=2, max_length=200)


class TanMechanismOut(BaseModel):
    code: str
    name: str
    decoupled: bool


class FinTsSessionOut(BaseModel):
    id: uuid.UUID
    fints_connection_id: uuid.UUID
    purpose: str
    status: FinTsSessionStatus
    tan_mechanism: str | None
    tan_mechanisms: list[TanMechanismOut]
    challenge_text: str | None
    challenge_hhduc: str | None
    challenge_image_mime: str | None
    challenge_image_base64: str | None
    challenge_decoupled: bool
    tan_pending: bool
    error_code: str | None
    error_message: str | None
    result: dict[str, Any]
    sync_run_id: uuid.UUID | None
    expires_at: datetime | None


class FinTsAccountOut(BaseModel):
    id: uuid.UUID
    iban_suffix: str
    bic: str | None
    account_number: str | None
    property_bank_account_id: uuid.UUID | None
    balance_booked: Decimal | None
    balance_currency: str | None
    balance_as_of: date | None
    balance_fetched_at: datetime | None
    last_transactions_fetch_at: datetime | None
    last_synced_booking_date: date | None


class FinTsConnectionOut(BaseModel):
    id: uuid.UUID
    bank_connection_id: uuid.UUID
    bank_name: str
    blz: str
    bic: str | None
    status: ConnectionStatus
    tan_mechanism: str | None
    tan_mechanisms: list[TanMechanismOut]
    last_sca_at: datetime | None
    sca_due: bool
    sca_due_on: date | None
    pin_blocked: bool
    last_error: str | None
    last_error_code: str | None
    last_sync_at: datetime | None
    open_session_id: uuid.UUID | None
    accounts: list[FinTsAccountOut]


def _institute_out(inst: fints_mod.Institute) -> InstituteOut:
    return InstituteOut(
        blz=inst.blz,
        name=inst.name,
        city=inst.city,
        bic=inst.bic,
        fints_url=inst.fints_url,
        connectable=inst.connectable,
    )


def _mechanisms_out(rows: list[dict[str, Any]]) -> list[TanMechanismOut]:
    return [
        TanMechanismOut(
            code=str(r.get("code")),
            name=str(r.get("name") or r.get("code")),
            decoupled=bool(r.get("decoupled")),
        )
        for r in rows
    ]


def _session_out(fs: FinTsSession, fc: FinTsConnection) -> FinTsSessionOut:
    return FinTsSessionOut(
        id=fs.id,
        fints_connection_id=fs.fints_connection_id,
        purpose=fs.purpose,
        status=fs.status,
        tan_mechanism=fs.tan_mechanism or fc.tan_mechanism,
        tan_mechanisms=_mechanisms_out(fc.tan_mechanisms),
        challenge_text=fs.challenge_text,
        challenge_hhduc=fs.challenge_hhduc,
        challenge_image_mime=fs.challenge_image_mime,
        challenge_image_base64=(
            base64.b64encode(fs.challenge_image).decode("ascii") if fs.challenge_image else None
        ),
        challenge_decoupled=fs.challenge_decoupled,
        tan_pending=fs.pending_tan is not None,
        error_code=fs.error_code,
        error_message=fs.error_message,
        result=fs.result or {},
        sync_run_id=fs.sync_run_id,
        expires_at=fs.expires_at,
    )


def _can_see_unassigned(principal: TenantPrincipal) -> bool:
    return principal.has("banking:approve") or principal.has("tenant_settings:update")


def _account_out(link: FinTsAccountLink) -> FinTsAccountOut:
    return FinTsAccountOut(
        id=link.id,
        iban_suffix=link.iban_suffix,
        bic=link.bic,
        account_number=link.account_number,
        property_bank_account_id=link.property_bank_account_id,
        balance_booked=link.balance_booked,
        balance_currency=link.balance_currency,
        balance_as_of=link.balance_as_of,
        balance_fetched_at=link.balance_fetched_at,
        last_transactions_fetch_at=link.last_transactions_fetch_at,
        last_synced_booking_date=link.last_synced_booking_date,
    )


async def _connection_out(
    session: Any, fc: FinTsConnection, conn: BankConnection, principal: TenantPrincipal
) -> FinTsConnectionOut:
    links = (
        await session.scalars(
            select(FinTsAccountLink)
            .where(FinTsAccountLink.fints_connection_id == fc.id)
            .order_by(FinTsAccountLink.iban_suffix)
        )
    ).all()
    show_all = _can_see_unassigned(principal)
    open_session = await session.scalar(
        select(FinTsSession.id)
        .where(FinTsSession.fints_connection_id == fc.id, FinTsSession.status.in_(OPEN_STATES))
        .order_by(FinTsSession.created_at.desc())
        .limit(1)
    )
    today = local_today()
    last_sca = fc.last_sca_at.date() if fc.last_sca_at else None
    return FinTsConnectionOut(
        id=fc.id,
        bank_connection_id=conn.id,
        bank_name=conn.bank_name,
        blz=fc.blz,
        bic=conn.bic,
        status=conn.status,
        tan_mechanism=fc.tan_mechanism,
        tan_mechanisms=_mechanisms_out(fc.tan_mechanisms),
        last_sca_at=fc.last_sca_at,
        sca_due=fints_mod.sca_due(last_sca, today),
        sca_due_on=last_sca + timedelta(days=fints_mod.SCA_VALID_DAYS) if last_sca else None,
        pin_blocked=fc.pin_blocked,
        last_error=fc.last_error,
        last_error_code=fc.last_error_code,
        last_sync_at=conn.last_sync_at,
        open_session_id=open_session,
        accounts=[
            _account_out(link)
            for link in links
            if show_all or link.property_bank_account_id is not None
        ],
    )


def _require_product_id(request: Request) -> None:
    if not request.app.state.settings.fints_product_id:
        raise ProblemError(ErrorCodes.FINTS_NOT_CONFIGURED)


def _queue_step(tenant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    from mhvp.banking.tasks import fints_step

    fints_step.delay(str(tenant_id), str(session_id))


async def _load(
    session: Any, fints_connection_id: uuid.UUID, *, lock: bool = False
) -> tuple[FinTsConnection, BankConnection]:
    fc = await session.get(FinTsConnection, fints_connection_id, with_for_update=lock)
    if fc is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    conn = await session.get(BankConnection, fc.bank_connection_id, with_for_update=lock)
    if conn is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return fc, conn


async def _ensure_no_open_session(session: Any, fc: FinTsConnection) -> None:
    open_id = await session.scalar(
        select(FinTsSession.id).where(
            FinTsSession.fints_connection_id == fc.id, FinTsSession.status.in_(OPEN_STATES)
        )
    )
    if open_id is not None:
        raise ProblemError(
            ErrorCodes.FINTS_STATE,
            detail="Für diese Bankverbindung läuft bereits eine TAN-Sitzung.",
        )


async def _new_session(
    session: Any,
    *,
    principal: TenantPrincipal,
    fc: FinTsConnection,
    conn: BankConnection,
    purpose: str,
    since: date | None = None,
    until: date | None = None,
    sync_run_id: uuid.UUID | None = None,
) -> FinTsSession:
    fs = FinTsSession(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        fints_connection_id=fc.id,
        purpose=purpose,
        status=FinTsSessionStatus.QUEUED,
        since=since,
        until=until,
        sync_run_id=sync_run_id,
        result={},
    )
    session.add(fs)
    await session.flush()
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="fints_session.queued",
        entity_type="bank_fints_session",
        entity_id=fs.id,
        actor_user_id=principal.user_id,
        payload={"purpose": purpose, "bank_connection_id": str(conn.id)},
    )
    return fs


@router.get("/config", summary="FinTS-Einrichtungsstatus (Produktregistrierung vorhanden)")
async def config(request: Request, principal: TenantPrincipal = Depends(READ)) -> FinTsConfigOut:
    return FinTsConfigOut(configured=bool(request.app.state.settings.fints_product_id))


@router.get(
    "/institutes",
    summary="Institutssuche (BLZ, BIC, IBAN oder Name)",
    dependencies=[Depends(strict_query)],
)
async def institutes(
    q: str = Query(min_length=2, max_length=60),
    principal: TenantPrincipal = Depends(READ),
) -> list[InstituteOut]:
    return [_institute_out(i) for i in fints_mod.search_institutes(q)]


@router.post("/connections", status_code=201, summary="Bank verbinden (FinTS PIN/TAN)")
async def create_connection(
    body: FinTsConnectionIn, request: Request, principal: TenantPrincipal = Depends(BANKING_APPROVE)
) -> FinTsSessionOut:
    """Stores login and PIN encrypted and queues the first dialog in the worker. The
    response is the session to poll; the bank's TAN request appears there."""
    _require_product_id(request)
    compact = fints_mod.normalise_query(body.institute)
    blz = fints_mod.blz_from_iban(compact) or (
        compact if compact.isdigit() and len(compact) == 8 else None
    )
    inst = fints_mod.find_institute(blz) if blz else None
    if inst is None:
        hits = fints_mod.search_institutes(compact, limit=2)
        inst = hits[0] if len(hits) == 1 else None
    if inst is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Institut nicht eindeutig gefunden.")
    if not inst.connectable or not inst.fints_url:
        raise ProblemError(ErrorCodes.FINTS_INSTITUTE_NOT_CONNECTABLE, detail=inst.name)
    async with tenant_tx(request, principal) as session:
        conn = BankConnection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            connector=Connector.FINTS,
            bank_name=body.bank_name or inst.name,
            bic=inst.bic,
            status=ConnectionStatus.NOT_CONFIGURED,
            sync_schedule="manual",
        )
        session.add(conn)
        await session.flush()
        fc = FinTsConnection(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            bank_connection_id=conn.id,
            blz=inst.blz,
            fints_url=inst.fints_url,
            login=body.login,
            pin=body.pin,
            tan_mechanism=body.tan_mechanism,
            tan_mechanisms=[],
        )
        session.add(fc)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="fints_connection.created",
            entity_type="bank_connection",
            entity_id=conn.id,
            actor_user_id=principal.user_id,
            payload={"blz": inst.blz, "bank_name": conn.bank_name},
        )
        fs = await _new_session(session, principal=principal, fc=fc, conn=conn, purpose="connect")
        out = _session_out(fs, fc)
        tenant_id, session_id = principal.tenant_id, fs.id
    _queue_step(tenant_id, session_id)
    return out


@router.post(
    "/connections/{fints_connection_id}/restart",
    status_code=201,
    summary="Neue TAN-Sitzung (PIN erneut eingeben oder TAN-Verfahren wechseln)",
)
async def restart_connection(
    fints_connection_id: uuid.UUID,
    body: RestartIn,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinTsSessionOut:
    _require_product_id(request)
    async with tenant_tx(request, principal) as session:
        fc, conn = await _load(session, fints_connection_id, lock=True)
        if conn.status == ConnectionStatus.DISABLED:
            raise ProblemError(ErrorCodes.FINTS_STATE, detail="Verbindung ist getrennt.")
        await _ensure_no_open_session(session, fc)
        if body.pin:
            fc.pin = body.pin
            fc.pin_blocked = False
        if fc.pin is None:
            raise ProblemError(ErrorCodes.FINTS_PIN_BLOCKED)
        if body.tan_mechanism:
            fc.tan_mechanism = body.tan_mechanism
        fc.updated_by = principal.user_id
        fs = await _new_session(session, principal=principal, fc=fc, conn=conn, purpose="connect")
        out = _session_out(fs, fc)
        tenant_id, session_id = principal.tenant_id, fs.id
    _queue_step(tenant_id, session_id)
    return out


@router.get(
    "/connections",
    summary="FinTS-Bankverbindungen mit Konten (ohne Zugangsdaten)",
    dependencies=[Depends(strict_query)],
)
async def list_connections(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[FinTsConnectionOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(FinTsConnection, BankConnection)
                .join(BankConnection, BankConnection.id == FinTsConnection.bank_connection_id)
                .order_by(FinTsConnection.created_at.desc())
            )
        ).all()
        return [await _connection_out(session, fc, conn, principal) for fc, conn in rows]


@router.get("/sessions/{session_id}", summary="TAN-Sitzung (Status, Challenge)")
async def get_session(
    session_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> FinTsSessionOut:
    async with tenant_tx(request, principal) as session:
        fs = await session.get(FinTsSession, session_id)
        if fs is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        fc = await session.get(FinTsConnection, fs.fints_connection_id)
        if fc is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if (
            fs.status in OPEN_STATES
            and fs.status != FinTsSessionStatus.QUEUED
            and fs.expires_at is not None
            and fs.expires_at < datetime.now(UTC)
            and fs.pending_tan is None
        ):
            fs.status = FinTsSessionStatus.FAILED
            fs.error_code = ErrorCodes.FINTS_STATE.code
            fs.error_message = "TAN-Sitzung abgelaufen, bitte erneut starten."
            fs.retry_data = fs.dialog_data = fs.client_data = None
            fs.challenge_image = None
        return _session_out(fs, fc)


@router.post("/sessions/{session_id}/tan", summary="TAN eingeben oder Freigabe abfragen")
async def submit_tan(
    session_id: uuid.UUID,
    body: TanIn,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinTsSessionOut:
    """`awaiting_tan` needs a TAN; `awaiting_decoupled` polls the confirmation in the bank
    app (no TAN). The TAN is held encrypted only until the worker picks the step up."""
    async with tenant_tx(request, principal) as session:
        fs = await session.get(FinTsSession, session_id, with_for_update=True)
        if fs is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        fc = await session.get(FinTsConnection, fs.fints_connection_id)
        if fc is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if fs.status == FinTsSessionStatus.AWAITING_TAN and not body.tan:
            raise ProblemError(ErrorCodes.VALIDATION, detail="TAN fehlt.")
        if fs.status not in (
            FinTsSessionStatus.AWAITING_TAN,
            FinTsSessionStatus.AWAITING_DECOUPLED,
        ):
            raise ProblemError(
                ErrorCodes.FINTS_STATE, detail="Die Sitzung wartet derzeit nicht auf eine TAN."
            )
        if fs.pending_tan is not None:
            raise ProblemError(
                ErrorCodes.FINTS_STATE, detail="Eine Eingabe wird bereits verarbeitet."
            )
        fs.pending_tan = body.tan if fs.status == FinTsSessionStatus.AWAITING_TAN else None
        fs.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="fints_session.tan_submitted",
            entity_type="bank_fints_session",
            entity_id=fs.id,
            actor_user_id=principal.user_id,
            payload={"decoupled": fs.status == FinTsSessionStatus.AWAITING_DECOUPLED},
        )
        await session.flush()
        out = _session_out(fs, fc)
        out.tan_pending = True
        tenant_id = principal.tenant_id
    _queue_step(tenant_id, session_id)
    return out


@router.post(
    "/connections/{fints_connection_id}/refresh",
    status_code=201,
    summary="Umsätze und Salden abrufen (neue Sitzung, ggf. TAN)",
)
async def refresh_connection(
    fints_connection_id: uuid.UUID,
    body: RefreshIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> FinTsSessionOut:
    """Balances for every reported account, transactions only for assigned accounts, from
    the account's cursor (minus an overlap) or the given range. The bank may ask for a TAN
    again (PSD2, 90 days): then the session waits like a connect session."""
    _require_product_id(request)
    async with tenant_tx(request, principal) as session:
        fc, conn = await _load(session, fints_connection_id, lock=True)
        if conn.status == ConnectionStatus.DISABLED:
            raise ProblemError(ErrorCodes.FINTS_STATE, detail="Verbindung ist getrennt.")
        if fc.pin_blocked or fc.pin is None:
            raise ProblemError(ErrorCodes.FINTS_PIN_BLOCKED)
        await _ensure_no_open_session(session, fc)
        links = (
            await session.scalars(
                select(FinTsAccountLink).where(
                    FinTsAccountLink.fints_connection_id == fc.id,
                    FinTsAccountLink.property_bank_account_id.is_not(None),
                )
            )
        ).all()
        since = body.since
        if since is None:
            cursors = [x.last_synced_booking_date for x in links]
            oldest = min((c for c in cursors if c is not None), default=None)
            since = fints_mod.initial_since(
                oldest if all(cursors) and cursors else None, local_today()
            )
        run = BankSyncRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            connection_id=conn.id,
            source="fints",
            status="queued",
            counts={},
        )
        session.add(run)
        await session.flush()
        fs = await _new_session(
            session,
            principal=principal,
            fc=fc,
            conn=conn,
            purpose="refresh",
            since=since,
            until=body.until,
            sync_run_id=run.id,
        )
        out = _session_out(fs, fc)
        tenant_id, session_id = principal.tenant_id, fs.id
    _queue_step(tenant_id, session_id)
    return out


@router.post("/accounts/{link_id}/assign", summary="Konto einem Objekt/Rechtsträger zuordnen")
async def assign_account(
    link_id: uuid.UUID,
    body: AssignIn,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> FinTsAccountOut:
    from mhvp.properties import services as prop_svc

    async with tenant_tx(request, principal) as session:
        link = await session.get(FinTsAccountLink, link_id, with_for_update=True)
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.property_bank_account_id is not None:
            target = await session.get(PropertyBankAccount, body.property_bank_account_id)
            if target is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Kein passendes internes Konto.")
            if target.iban_fingerprint != link.iban_fingerprint:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Die IBAN des internen Kontos stimmt nicht mit dem Bankkonto überein.",
                )
        else:
            if not (body.property_id and body.legal_entity_id and body.kind and body.holder):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Objekt, Rechtsträger, Kontoart und Kontoinhaber sind nötig.",
                )
            prop = await session.get(Property, body.property_id)
            entity = await session.get(LegalEntity, body.legal_entity_id)
            if prop is None or entity is None or entity.property_id != prop.id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Der Rechtsträger gehört nicht zu diesem Objekt."
                )
            if entity.kind not in prop_svc.ACCOUNT_OWNERS[body.kind]:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=(
                        f"Ein Konto der Art {body.kind.value} kann nicht dem Rechtsträger "
                        f"{entity.kind.value} gehören (6.9.1)."
                    ),
                )
            iban = normalise_iban(link.iban)
            target = PropertyBankAccount(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                property_id=prop.id,
                legal_entity_id=entity.id,
                kind=body.kind,
                iban=iban,
                iban_suffix=iban[-4:],
                iban_fingerprint=crypto.fingerprint(iban),
                bic=link.bic,
                holder=body.holder,
                segregated=body.kind is BankAccountKind.DEPOSIT,
                valid_from=local_today(),
            )
            session.add(target)
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="property_bank_account.created",
                entity_type="property_bank_account",
                entity_id=target.id,
                actor_user_id=principal.user_id,
                payload={
                    "kind": body.kind.value,
                    "legal_entity_id": str(entity.id),
                    "source": "fints",
                },
            )
        link.property_bank_account_id = target.id
        link.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="fints_account.assigned",
            entity_type="fints_account_link",
            entity_id=link.id,
            actor_user_id=principal.user_id,
            payload={"property_bank_account_id": str(target.id)},
        )
        await session.flush()
        return _account_out(link)


@router.delete("/connections/{fints_connection_id}", status_code=204, summary="Verbindung trennen")
async def delete_connection(
    fints_connection_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(BANKING_APPROVE),
) -> None:
    """Wipes PIN, client state and every session blob; the connection row stays as
    `disabled` for traceability (imported transactions keep their sync run reference)."""
    async with tenant_tx(request, principal) as session:
        fc, conn = await _load(session, fints_connection_id, lock=True)
        await session.execute(delete(FinTsSession).where(FinTsSession.fints_connection_id == fc.id))
        fc.pin = None
        fc.client_data = None
        fc.pin_blocked = False
        fc.updated_by = principal.user_id
        conn.status = ConnectionStatus.DISABLED
        conn.credentials = None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="fints_connection.disconnected",
            entity_type="bank_connection",
            entity_id=conn.id,
            actor_user_id=principal.user_id,
        )
        await session.flush()
