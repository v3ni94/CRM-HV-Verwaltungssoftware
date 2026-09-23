"""Portal endpoints (/api/v1/portal, M21 tenants and owners, M22 providers) and management
endpoints (/api/v1/portal-admin). Portal users hold the role portal_user without CRM rights;
every portal read goes through the access matrix (6.9.6)."""

import hashlib
import json
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import (
    TenantPrincipal,
    get_principal,
    require_permission,
    sessions,
    tenant_tx,
)
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access
from mhvp.portal.models import ChangeRequest, PortalAccount
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin", tags=["Portal Verwaltung"])
MANAGE = require_permission("contacts:update")
INVITE_DAYS = 14
KINDS = ("address", "phone", "email", "bank_account", "meter_reading", "invoice_submission")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PortalInviteIn(_In):
    contact_id: uuid.UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)


class PortalAcceptIn(_In):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class PortalTicketIn(_In):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=20000)
    unit_id: uuid.UUID | None = None


class PortalCommentIn(_In):
    body: str = Field(min_length=1, max_length=20000)


class PortalChangeIn(_In):
    kind: str = Field(pattern="^(address|phone|email|bank_account)$")
    payload: dict[str, str]


class PortalMeterIn(_In):
    meter_id: uuid.UUID
    value: Decimal = Field(ge=0)
    read_at: date


class PortalDecideIn(_In):
    accept: bool
    note: str | None = Field(default=None, max_length=2000)


class PortalQuoteIn(_In):
    amount: Decimal = Field(gt=0)
    document_id: uuid.UUID | None = None


class PortalAppointmentIn(_In):
    scheduled_at: datetime


class PortalCompleteIn(_In):
    report: str = Field(min_length=3, max_length=20000)
    photo_document_ids: list[uuid.UUID] = Field(default_factory=list)


class PortalInvoiceSubmitIn(_In):
    number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    gross: Decimal = Field(gt=0)
    document_id: uuid.UUID


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# Management -----------------------------------------------------------------------------


@admin.post("/accounts", status_code=201, summary="Portalzugang einladen")
async def invite(
    body: PortalInviteIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    from mhvp.contacts.models import Contact
    from mhvp.platform import services as platform
    from mhvp.platform.models import User

    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, body.contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if await session.scalar(
            select(PortalAccount.id).where(PortalAccount.contact_id == body.contact_id)
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Für den Kontakt besteht bereits ein Portalzugang."
            )
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        email = body.email.strip().lower()
        if await session.scalar(select(User.id).where(User.email == email)):
            raise ProblemError(ErrorCodes.CONFLICT, detail="E-Mail-Adresse bereits registriert.")
        user = User(email=email, display_name=body.display_name, password_hash=None)
        session.add(user)
        await session.flush()
        user_id = user.id
    await platform.add_member(
        factory,
        tenant_id=principal.tenant_id,
        user_id=user_id,
        role_codes=["portal_user"],
        actor_user_id=principal.user_id,
    )
    secret = secrets.token_urlsafe(32)
    async with tenant_tx(request, principal) as session:
        account = PortalAccount(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            user_id=user_id,
            contact_id=body.contact_id,
            invitation_hash=_hash(secret),
            invitation_expires_at=datetime.now(UTC) + timedelta(days=INVITE_DAYS),
        )
        session.add(account)
        await session.flush()
        grants = await access.sync_grants(session, account)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_account.invited",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"grants": grants},
        )
        # The token goes into the invitation letter or mail (M23); it is shown once here.
        return {
            "id": account.id,
            "user_id": user_id,
            "grants": grants,
            "invitation_token": f"{principal.tenant_id.hex}.{secret}",
        }


@admin.post("/accounts/{account_id}/sync-grants", summary="Zugriffsrechte neu ableiten")
async def resync(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        account = await session.get(PortalAccount, account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {"grants": await access.sync_grants(session, account)}


@admin.get("/change-requests", summary="Vorschläge aus dem Portal")
async def change_requests(
    request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ChangeRequest).order_by(ChangeRequest.created_at.desc()).limit(500)
        )
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "payload": json.loads(r.payload),
                "account_id": r.account_id,
            }
            for r in rows.all()
        ]


@admin.post("/change-requests/{request_id}/decide", summary="Vorschlag annehmen oder ablehnen")
async def decide(
    request_id: uuid.UUID,
    body: PortalDecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    from mhvp.contacts.models import ContactBankAccount, ContactEmail, ContactPhone, PhoneLabel
    from mhvp.properties.models import MeterReading, ReadingSource

    async with tenant_tx(request, principal) as session:
        row = await session.get(ChangeRequest, request_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "proposed":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits entschieden.")
        account = await session.get(PortalAccount, row.account_id)
        payload = json.loads(row.payload)
        if body.accept and account is not None:
            if row.kind == "email":
                session.add(
                    ContactEmail(
                        tenant_id=row.tenant_id,
                        contact_id=account.contact_id,
                        email=payload["email"],
                    )
                )
            elif row.kind == "phone":
                session.add(
                    ContactPhone(
                        tenant_id=row.tenant_id,
                        contact_id=account.contact_id,
                        label=PhoneLabel.OTHER,
                        number=payload["number"],
                    )
                )
            elif row.kind == "meter_reading":
                session.add(
                    MeterReading(
                        tenant_id=row.tenant_id,
                        meter_id=uuid.UUID(payload["meter_id"]),
                        value=Decimal(payload["value"]),
                        read_at=date.fromisoformat(payload["read_at"]),
                        source=ReadingSource.PORTAL,
                    )
                )
            elif row.kind == "bank_account":
                from mhvp.contacts.validation import normalise_iban
                from mhvp.core import crypto

                iban = normalise_iban(payload["iban"])
                session.add(
                    ContactBankAccount(
                        tenant_id=row.tenant_id,
                        contact_id=account.contact_id,
                        iban=iban,
                        iban_suffix=iban[-4:],
                        iban_fingerprint=crypto.fingerprint(iban),
                        valid_from=local_today(),
                    )
                )
            # address and invoice submissions are applied manually in the CRM (M21-02, M22-01)
        row.status, row.decided_by, row.decision_note = (
            ("accepted" if body.accept else "rejected"),
            principal.user_id,
            body.note,
        )
        await session.flush()
        return {"id": row.id, "status": row.status}


# Portal ---------------------------------------------------------------------------------


@router.post("/invitations/accept", summary="Einladung annehmen und Passwort setzen")
async def accept(body: PortalAcceptIn, request: Request) -> dict[str, str]:
    from mhvp.core.auth import passwords
    from mhvp.platform.models import User

    try:
        tenant_hex, secret = body.token.split(".", 1)
        tenant_id = uuid.UUID(hex=tenant_hex)
    except ValueError:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Einladung ungültig.") from None
    violation = passwords.policy_violation(body.password)
    if violation:
        raise ProblemError(ErrorCodes.PASSWORD_POLICY, detail=violation)
    factory = sessions(request)
    async with tenant_transaction(factory, tenant_id) as session:
        account = await session.scalar(
            select(PortalAccount)
            .where(PortalAccount.invitation_hash == _hash(secret))
            .with_for_update()
        )
        if (
            account is None
            or account.invitation_expires_at is None
            or account.invitation_expires_at < datetime.now(UTC)
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Einladung ungültig oder abgelaufen.")
        account.status, account.activated_at, account.invitation_hash = (
            "active",
            datetime.now(UTC),
            None,
        )
        user_id = account.user_id
    async with platform_transaction(factory) as session:
        user = await session.get(User, user_id)
        if user is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        user.password_hash = passwords.hash_password(body.password)
    return {"status": "active"}


async def portal_user(request: Request) -> tuple[TenantPrincipal, PortalAccount]:
    principal = await get_principal(request)
    if principal.tenant_id is None or principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN)
    tp = TenantPrincipal(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        permissions=principal.permissions,
        roles=principal.roles,
    )
    async with tenant_tx(request, tp) as session:
        account = await session.scalar(
            select(PortalAccount).where(
                PortalAccount.user_id == principal.user_id, PortalAccount.status == "active"
            )
        )
    if account is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No active portal account.")
    return tp, account


Portal = tuple[TenantPrincipal, PortalAccount]


async def _scopes(session: AsyncSession, account: PortalAccount) -> dict[str, set[uuid.UUID]]:
    out: dict[str, set[uuid.UUID]] = {}
    for g in await access.grants(session, account, local_today()):
        out.setdefault(g.scope_type, set()).add(g.scope_id)
    return out


@router.get("/me", summary="Eigene Rollen und Verträge")
async def me(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.contracts.models import Contract
    from mhvp.tickets.models import WorkOrder

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        active = await access.grants(session, account, local_today())
        is_provider = (
            await session.scalar(
                select(WorkOrder.id)
                .where(WorkOrder.provider_contact_id == account.contact_id)
                .limit(1)
            )
            is not None
        )
        contract_ids = [g.scope_id for g in active if g.scope_type == "contract"]
        contracts = (
            (await session.scalars(select(Contract).where(Contract.id.in_(contract_ids)))).all()
            if contract_ids
            else []
        )
        return {
            "contact_id": account.contact_id,
            "roles": sorted({g.role for g in active} | ({"provider"} if is_provider else set())),
            "contracts": [
                {
                    "id": c.id,
                    "kind": c.kind.value,
                    "number": c.number,
                    "unit_id": c.unit_id,
                    "start_date": c.start_date,
                    "end_date": c.end_date,
                }
                for c in contracts
            ],
        }


@router.get("/documents", summary="Freigegebene Dokumente")
async def documents(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        docs = await access.visible_documents(session, account, local_today())
        return [
            {"id": d.id, "title": d.title, "filename": d.filename, "created_at": d.created_at}
            for d in docs
        ]


@router.get("/documents/{document_id}/download", summary="Dokument herunterladen (gleiche Prüfung)")
async def download(
    document_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    from mhvp.documents.blobs import BlobStore

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        docs = {d.id: d for d in await access.visible_documents(session, account, local_today())}
        document = docs.get(document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.portal_download",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(account.id)},
        )
        return Response(
            content=data,
            media_type=document.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
        )


@router.post("/uploads", status_code=201, summary="Datei hochladen (Foto, Angebot, Rechnung)")
async def upload(
    request: Request, file: UploadFile = File(), ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import check_upload, store_document

    principal, account = ctx
    data = await file.read()
    mime = file.content_type or "application/octet-stream"
    check_upload(mime, data, request.app.state.settings.document_max_bytes)
    async with tenant_tx(request, principal) as session:
        doc = await store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=data,
            title=file.filename or "upload",
            filename=file.filename or "upload",
            mime_type=mime,
            source=DocumentSource.PORTAL,
            category_id=None,
            links=[("contact", account.contact_id, LinkRole.ORIGINAL)],
            created_by=principal.user_id,
            visibility=["provider"],
        )
        return {"id": doc.id}


@router.post("/tickets", status_code=201, summary="Schadensmeldung")
async def create_ticket(
    body: PortalTicketIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.core.numbering import next_number
    from mhvp.properties.models import Unit
    from mhvp.tickets.models import Priority, Ticket, TicketSource
    from mhvp.tickets.routers import SLA_HOURS

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        scopes = await _scopes(session, account)
        property_id = None
        if body.unit_id is not None:
            if body.unit_id not in scopes.get("unit", set()):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN, detail="Die Einheit gehört nicht zu Ihren Verträgen."
                )
            unit = await session.get(Unit, body.unit_id)
            property_id = unit.property_id if unit else None
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            title=body.title,
            public_description=body.description,
            unit_id=body.unit_id,
            property_id=property_id,
            initiator_contact_id=account.contact_id,
            source=TicketSource.PORTAL,
            visible_for=["initiator"],
            sla_due_at=datetime.now(UTC) + timedelta(hours=SLA_HOURS[Priority.NORMAL]),
        )
        session.add(ticket)
        await session.flush()
        return {"id": ticket.id, "number": ticket.number, "status": ticket.status.value}


@router.get("/tickets", summary="Eigene Meldungen mit Verlauf")
async def tickets(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    from mhvp.tickets.models import Ticket, TicketComment

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(Ticket)
                .where(Ticket.initiator_contact_id == account.contact_id)
                .order_by(Ticket.number.desc())
            )
        ).all()
        out = []
        for t in rows:
            comments = (
                await session.scalars(
                    select(TicketComment)
                    .where(TicketComment.ticket_id == t.id, TicketComment.internal.is_(False))
                    .order_by(TicketComment.created_at)
                )
            ).all()
            out.append(
                {
                    "id": t.id,
                    "number": t.number,
                    "title": t.title,
                    "status": t.status.value,
                    "comments": [c.body for c in comments],
                }
            )
        return out


@router.post(
    "/tickets/{ticket_id}/comments", status_code=201, summary="Kommentar zur eigenen Meldung"
)
async def comment(
    ticket_id: uuid.UUID,
    body: PortalCommentIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.tickets.models import Ticket, TicketComment

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None or ticket.initiator_contact_id != account.contact_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = TicketComment(
            tenant_id=principal.tenant_id,
            ticket_id=ticket.id,
            internal=False,
            author_contact_id=account.contact_id,
            body=body.body,
        )
        session.add(row)
        await session.flush()
        return {"id": row.id}


async def _propose(
    session: AsyncSession,
    principal: TenantPrincipal,
    account: PortalAccount,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    row = ChangeRequest(
        tenant_id=principal.tenant_id,
        account_id=account.id,
        kind=kind,
        payload=json.dumps(payload, default=str),
    )
    session.add(row)
    await session.flush()
    return {"id": row.id, "kind": kind, "status": row.status}


@router.post(
    "/change-requests",
    status_code=201,
    summary="Änderung der Stammdaten oder Bankverbindung vorschlagen",
)
async def propose(
    body: PortalChangeIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        return await _propose(session, principal, account, body.kind, body.payload)


@router.post("/meter-readings", status_code=201, summary="Zählerstand melden (Vorschlag)")
async def meter_reading(
    body: PortalMeterIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.properties.models import Meter

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        meter = await session.get(Meter, body.meter_id)
        if meter is None or meter.unit_id not in (await _scopes(session, account)).get(
            "unit", set()
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _propose(
            session, principal, account, "meter_reading", body.model_dump(mode="json")
        )


@router.get("/account", summary="Kontoauszug: offene Posten der eigenen Verträge")
async def statement(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import Ledger, LedgerAccount
    from mhvp.contracts.models import Contract, DebtorAccountReservation

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        contract_ids = (await _scopes(session, account)).get("contract", set())
        items: list[dict[str, Any]] = []
        leading = True
        for contract in (
            (await session.scalars(select(Contract).where(Contract.id.in_(contract_ids)))).all()
            if contract_ids
            else []
        ):
            reservation = await session.get(DebtorAccountReservation, contract.debtor_account_id)
            ledger = await session.scalar(
                select(Ledger).where(Ledger.legal_entity_id == contract.legal_entity_id)
            )
            if reservation is None or ledger is None:
                continue
            debtor = await session.scalar(
                select(LedgerAccount).where(
                    LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == reservation.number
                )
            )
            if debtor is None:
                continue
            leading = leading and ledger.leading_system.value == "mhvp"
            for i in await acc.open_items(session, ledger, local_today(), debtor.id):
                items.append(
                    {
                        "contract_number": contract.number,
                        "due_date": i["due_date"],
                        "amount": i["amount"],
                        "remaining": i["remaining"],
                    }
                )
        return {
            "items": items,
            "note": None
            if leading
            else "Vorläufig: Die führende Buchhaltung ist noch das Altsystem.",
        }


# Providers (M22) ------------------------------------------------------------------------


async def _own_order(session: AsyncSession, account: PortalAccount, order_id: uuid.UUID) -> Any:
    from mhvp.tickets.models import WorkOrder

    order = await session.get(WorkOrder, order_id, with_for_update=True)
    if order is None or order.provider_contact_id != account.contact_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return order


async def _step(
    session: AsyncSession, order: Any, target: Any, principal: TenantPrincipal, note: str
) -> None:
    from mhvp.tickets.models import WorkOrderEvent
    from mhvp.tickets.routers import ORDER_FLOW

    if target not in ORDER_FLOW[order.status]:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=f"Schritt {order.status.value} nach {target.value} nicht zulässig.",
        )
    session.add(
        WorkOrderEvent(
            tenant_id=order.tenant_id,
            work_order_id=order.id,
            from_status=order.status.value,
            to_status=target.value,
            user_id=principal.user_id,
            note=f"Portal: {note}",
        )
    )
    order.status = target


def _order(o: Any) -> dict[str, Any]:
    return {
        "id": o.id,
        "description": o.description,
        "status": o.status.value,
        "quote_amount": o.quote_amount,
        "scheduled_at": o.scheduled_at,
    }


@router.get("/work-orders", summary="Eigene Aufträge (Dienstleister)")
async def work_orders(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    from mhvp.tickets.models import WorkOrder

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(WorkOrder)
            .where(WorkOrder.provider_contact_id == account.contact_id)
            .order_by(WorkOrder.created_at.desc())
        )
        return [_order(o) for o in rows.all()]


@router.post("/work-orders/{order_id}/decline", summary="Auftrag ablehnen")
async def decline(
    order_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        await _step(session, order, OrderStatus.REJECTED, principal, "abgelehnt")
        return _order(order)


@router.post("/work-orders/{order_id}/quote", summary="Angebot abgeben")
async def quote(
    order_id: uuid.UUID, body: PortalQuoteIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        await _step(session, order, OrderStatus.QUOTED, principal, "Angebot")
        order.quote_amount, order.quote_document_id = body.amount, body.document_id
        return _order(order)


@router.post("/work-orders/{order_id}/appointment", summary="Termin festlegen (nach Freigabe)")
async def appointment(
    order_id: uuid.UUID,
    body: PortalAppointmentIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        await _step(session, order, OrderStatus.SCHEDULED, principal, "Termin")
        order.scheduled_at = body.scheduled_at
        return _order(order)


@router.post("/work-orders/{order_id}/complete", summary="Ausführung dokumentieren")
async def complete(
    order_id: uuid.UUID,
    body: PortalCompleteIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if order.status is OrderStatus.SCHEDULED:
            await _step(session, order, OrderStatus.IN_PROGRESS, principal, "Beginn")
        await _step(session, order, OrderStatus.DONE, principal, "ausgeführt")
        order.completion_report, order.photo_document_ids = body.report, body.photo_document_ids
        return _order(order)


@router.post(
    "/work-orders/{order_id}/invoice", status_code=201, summary="Rechnung einreichen (zur Prüfung)"
)
async def submit_invoice(
    order_id: uuid.UUID,
    body: PortalInvoiceSubmitIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if order.status.value != "done":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Rechnung erst nach dokumentierter Ausführung."
            )
        return await _propose(
            session,
            principal,
            account,
            "invoice_submission",
            {**body.model_dump(mode="json"), "work_order_id": str(order.id)},
        )
