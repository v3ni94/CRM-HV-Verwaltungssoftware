"""Portal endpoints (/api/v1/portal, M21 tenants and owners, M22 providers) and management
endpoints (/api/v1/portal-admin). Portal users hold the role portal_user without CRM rights;
every portal read goes through the access matrix (6.9.6)."""

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote as url_quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth import service as auth_service
from mhvp.core.auth.principal import (
    TenantPrincipal,
    get_principal,
    require_permission,
    resolve_host_tenant,
    sessions,
    tenant_tx,
)
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access, magic_link, read_receipts
from mhvp.portal.models import ChangeRequest, PortalAccount
from mhvp.workspace.models import Notification
from mhvp.workspace.routers import NotificationOut, notification_out
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin", tags=["Portal Verwaltung"])
MANAGE = require_permission("contacts:update")
INVITE_DAYS = 14
# M21-01: the QR invitation code printed on the letter is valid longer than the e-mail
# invitation (INVITE_DAYS) because a letter reaches the recipient by post, days after issuing;
# Produktschutz, docs/rules M21-01, not a legal deadline.
QR_INVITE_DAYS = 90
KINDS = ("address", "phone", "email", "bank_account", "meter_reading", "invoice_submission")
# A55: the portal accepts photos and PDF only (damage report, quote, invoice); other types of
# the general document pipeline (text, CSV, XML) stay CRM side.
PORTAL_UPLOAD_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/tiff", "image/heic", "application/pdf"}
)


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
    # A55: photos or PDFs uploaded by this portal account via POST /portal/uploads; linked to
    # the ticket as attachments (entity_type "ticket"). Never a document of someone else.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


class PortalCommentIn(_In):
    body: str = Field(min_length=1, max_length=20000)


class PortalChangeIn(_In):
    kind: str = Field(pattern="^(address|phone|email|bank_account)$")
    # address (M21-02): street, house_number, postal_code, city, optional addition and
    # country, valid_from (ISO date, required), optional document_id of an own upload as
    # evidence (registration certificate). Other kinds keep their single value.
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


class PortalProposalIn(_In):
    starts_at: datetime
    note: str | None = Field(default=None, max_length=500)


class PortalProposalsIn(_In):
    """A58: one round of up to three appointment proposals; a new round supersedes the open
    proposals of the previous round."""

    proposals: list[PortalProposalIn] = Field(min_length=1, max_length=3)


class PortalCompleteIn(_In):
    report: str = Field(min_length=3, max_length=20000)
    # A58: photos of the execution, uploaded by this account via POST /portal/uploads and linked
    # to the order as attachments (same ownership rule as ticket photos, A55).
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    # Kept for older portal clients; merged into document_ids.
    photo_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class PortalInvoiceSubmitIn(_In):
    number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    gross: Decimal = Field(gt=0)
    document_id: uuid.UUID


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def invitation_url(request: Request, token: str) -> str | None:
    """Public link to the portal's invitation page with the one time code (A56)."""
    base = getattr(request.app.state.settings, "web_portal_url", None)
    return f"{str(base).rstrip('/')}/einladung?code={url_quote(token)}" if base else None


# Management -----------------------------------------------------------------------------


async def provision_account(
    request: Request,
    principal: TenantPrincipal,
    *,
    contact_id: uuid.UUID,
    email: str,
    display_name: str,
) -> dict[str, Any]:
    """Create the platform user (role portal_user), the portal account and the derived grants.

    Shared by the invitation endpoint and the handover participant access (M30 stage 3). The
    invitation token is returned once; it goes into the invitation letter or mail (M23)."""
    from mhvp.contacts.models import Contact
    from mhvp.platform import services as platform
    from mhvp.platform.models import User

    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, contact_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if await session.scalar(
            select(PortalAccount.id).where(PortalAccount.contact_id == contact_id)
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Für den Kontakt besteht bereits ein Portalzugang."
            )
    factory = sessions(request)
    async with platform_transaction(factory) as session:
        email = email.strip().lower()
        existing_user_id = await session.scalar(select(User.id).where(User.email == email))
    if existing_user_id is not None:
        async with tenant_tx(request, principal) as session:
            existing_account = await session.scalar(
                select(PortalAccount).where(
                    PortalAccount.tenant_id == principal.tenant_id,
                    PortalAccount.user_id == existing_user_id,
                )
            )
            if existing_account is not None and await access.has_staff_grant(
                session, existing_account.id
            ):
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=(
                        "Für dieses Konto besteht bereits ein interner Mitarbeiterzugang. "
                        "Externe Portalrechte (Eigentümer, Mieter, Dienstleister) können "
                        "diesem Konto nicht zusätzlich zugewiesen werden."
                    ),
                )
        raise ProblemError(ErrorCodes.CONFLICT, detail="E-Mail-Adresse bereits registriert.")
    async with platform_transaction(factory) as session:
        user = User(email=email, display_name=display_name, password_hash=None)
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
            contact_id=contact_id,
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
        token = f"{principal.tenant_id.hex}.{secret}"
        return {
            "id": account.id,
            "user_id": user_id,
            "grants": grants,
            "invitation_token": token,
            # A56: link to the portal's invitation page (shown as text and QR in the CRM); None
            # when no public portal URL is configured.
            "invitation_url": invitation_url(request, token),
        }


class PortalAccountOut(BaseModel):
    """Portal account of a contact as the CRM sees it (A86). Never carries the invitation
    hash, a password hash or a token; ``status`` is the account status of the model
    (``invited`` until the invitation is accepted, then ``active``), ``locked`` mirrors a
    temporary login lock of the platform user."""

    id: uuid.UUID
    contact_id: uuid.UUID
    email: str
    status: str
    locked: bool
    invited_at: datetime
    invitation_expires_at: datetime | None
    activated_at: datetime | None
    last_login_at: datetime | None
    # M21-01: optional e-mail code second factor on top of the magic link login.
    magic_link_2fa: bool


@admin.get("/accounts", summary="Portalzugänge eines Kontakts")
async def list_accounts(
    contact_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("contacts:read")),
) -> list[PortalAccountOut]:
    """Portal accounts of one contact of the own tenant (RLS); an unknown or foreign contact
    yields an empty list, never 404, so the CRM can show "kein Zugang" without a probe."""
    from mhvp.platform.models import User

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(PortalAccount, User)
                .join(User, User.id == PortalAccount.user_id)
                .where(PortalAccount.contact_id == contact_id)
                .order_by(PortalAccount.created_at)
            )
        ).all()
        now = datetime.now(UTC)
        return [
            PortalAccountOut(
                id=account.id,
                contact_id=account.contact_id,
                email=user.email,
                status=account.status,
                locked=bool(
                    not user.active or (user.locked_until is not None and user.locked_until > now)
                ),
                invited_at=account.created_at,
                invitation_expires_at=account.invitation_expires_at,
                activated_at=account.activated_at,
                last_login_at=user.last_login_at,
                magic_link_2fa=account.magic_link_2fa,
            )
            for account, user in rows
        ]


@admin.post("/accounts", status_code=201, summary="Portalzugang einladen")
async def invite(
    body: PortalInviteIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    return await provision_account(
        request,
        principal,
        contact_id=body.contact_id,
        email=body.email,
        display_name=body.display_name,
    )


@admin.post("/accounts/{account_id}/sync-grants", summary="Zugriffsrechte neu ableiten")
async def resync(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        account = await session.get(PortalAccount, account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {"grants": await access.sync_grants(session, account)}


class PortalSecurityIn(_In):
    magic_link_2fa: bool


@admin.patch("/accounts/{account_id}/security", status_code=204, summary="Sicherheitsoptionen")
async def set_security(
    account_id: uuid.UUID,
    body: PortalSecurityIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> Response:
    """Switches the optional e-mail code second factor of the magic link login on or off
    (M21-01); off by default, never mandatory (mirrors TOTP, operator 26.09.2026, M2-01)."""
    async with tenant_tx(request, principal) as session:
        account = await session.get(PortalAccount, account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        account.magic_link_2fa = body.magic_link_2fa
    return Response(status_code=204)


def _invitation_letter_text(
    *, name: str | None, token: str, expires_at: datetime | None, portal_url: str | None
) -> tuple[str, str]:
    """Subject and body of the printed invitation letter (M21-01), shared with the QR code
    printed below it. The code exists in clear text only while this text and the PDF are
    built; it is stored as a hash (rule 0.1.13)."""
    greeting = f"Guten Tag {name}," if name else "Guten Tag,"
    where = (
        f"Bitte rufen Sie das Kundenportal unter {portal_url} auf"
        if portal_url
        else "Bitte rufen Sie das Kundenportal der Verwaltung auf"
    )
    valid = (
        f"Der Einladungscode ist bis zum {expires_at.astimezone(UTC):%d.%m.%Y} gültig und kann "
        "nur einmal verwendet werden."
        if expires_at is not None
        else "Der Einladungscode kann nur einmal verwendet werden."
    )
    body = (
        f"{greeting}\n\n"
        "für Sie wurde ein Zugang zum Kundenportal eingerichtet. Dort erhalten Sie Ihre "
        "Unterlagen, können Anliegen melden und Zählerstände mitteilen.\n\n"
        f"{where} und geben Sie bei der Aktivierung den folgenden Einladungscode ein:\n"
        f"{token}\n\n"
        f"{valid}\n\n"
        "Bei der Aktivierung vergeben Sie ein Passwort. Für die künftige Anmeldung genügt "
        "wahlweise auch ein einmaliger Link, den Sie sich im Portal an Ihre E-Mail-Adresse "
        "senden lassen können.\n\n"
        "Bitte geben Sie den Einladungscode nicht an Dritte weiter."
    )
    return "Zugang zum Kundenportal", body


def _invitation_qr(url: str | None) -> Any:
    from mhvp.documents import letters

    if not url:
        return None
    return letters.LetterQr(
        payload=url, caption="Einladungslink zum Scannen mit dem Smartphone oder zum Eingeben:"
    )


@admin.post(
    "/accounts/{account_id}/invitation-letter",
    summary="Einladung als Anschreiben (PDF, neuer Einladungscode, 90 Tage gültig)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def invitation_letter(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> Response:
    """Letter on the tenant letterhead (M6 renderer) with a QR invitation code, for contacts
    reached by post. POST, not GET: issuing the letter rotates the invitation code (a prefetch
    must not invalidate a code already handed out); the code is valid 90 days (``QR_INVITE_DAYS``,
    longer than the e-mail invitation) because a letter reaches the recipient with a delay."""
    from mhvp.documents import letters
    from mhvp.documents import services as documents_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.platform.models import User
    from mhvp.workspace.services import local_today

    portal_base = getattr(request.app.state.settings, "web_portal_url", None)
    portal_base = str(portal_base).rstrip("/") if portal_base else None
    async with tenant_tx(request, principal) as session:
        account = await session.get(PortalAccount, account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        head = await documents_services.letterhead(session, BlobStore(request.app.state.settings))
        secret = secrets.token_urlsafe(32)
        account.invitation_hash = _hash(secret)
        account.invitation_expires_at = datetime.now(UTC) + timedelta(days=QR_INVITE_DAYS)
        token = f"{principal.tenant_id.hex}.{secret}"
        name: str | None
        try:
            _contact, lines, _data = await documents_services.recipient(session, account.contact_id)
            name = lines[0]
        except ProblemError:
            user = await session.scalar(select(User.display_name).where(User.id == account.user_id))
            lines, name = [user or ""], user
        subject, text = _invitation_letter_text(
            name=name, token=token, expires_at=account.invitation_expires_at, portal_url=portal_base
        )
        content = letters.render_pdf(
            head,
            letters.Letter(
                recipient_lines=lines,
                subject=letters.render_text("{{ s }}", {"s": subject}),
                body=letters.render_text("{{ b }}", {"b": text}),
                letter_date=local_today(),
                qr=_invitation_qr(invitation_url(request, token)),
            ),
        )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_account.invitation_letter",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={},
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "content-disposition": 'attachment; filename="einladung-kundenportal.pdf"',
            "cache-control": "no-store",
        },
    )


@admin.get("/change-requests", summary="Vorschläge aus dem Portal")
async def change_requests(
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
    contact_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(ChangeRequest, PortalAccount.contact_id).join(
            PortalAccount, PortalAccount.id == ChangeRequest.account_id
        )
        if contact_id is not None:
            query = query.where(PortalAccount.contact_id == contact_id)
        if status is not None:
            query = query.where(ChangeRequest.status == status)
        rows = await session.execute(query.order_by(ChangeRequest.created_at.desc()).limit(500))
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "payload": json.loads(r.payload),
                "account_id": r.account_id,
                "contact_id": cid,
                "created_at": r.created_at,
                "decision_note": r.decision_note,
            }
            for r, cid in rows.all()
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
            elif row.kind == "address":
                await _apply_address(session, principal, row, account.contact_id, payload)
            # invoice submissions are applied manually in the CRM (M22-01)
        row.status, row.decided_by, row.decision_note = (
            ("accepted" if body.accept else "rejected"),
            principal.user_id,
            body.note,
        )
        await session.flush()
        return {"id": row.id, "status": row.status}


async def _apply_address(
    session: AsyncSession,
    principal: TenantPrincipal,
    row: ChangeRequest,
    contact_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """M21-02: the accepted proposal becomes a postal address of the contact with its date of
    validity. When the date has come it becomes the primary address, otherwise it is stored
    beside the current one (the staff member switches it on the date); the change is
    written as event ``contact.address_changed``."""
    from mhvp.contacts.models import AddressLabel, ContactAddress

    valid_from = date.fromisoformat(payload["valid_from"])
    due = valid_from <= local_today()
    if due:
        await session.execute(
            update(ContactAddress)
            .where(ContactAddress.contact_id == contact_id, ContactAddress.is_primary.is_(True))
            .values(is_primary=False)
        )
    address = ContactAddress(
        tenant_id=row.tenant_id,
        contact_id=contact_id,
        label=AddressLabel.POSTAL,
        street=payload.get("street") or None,
        house_number=payload.get("house_number") or None,
        postal_code=payload.get("postal_code") or None,
        city=payload.get("city") or None,
        addition=payload.get("addition") or None,
        country=payload.get("country") or "DE",
        is_primary=due,
        valid_from=valid_from,
    )
    session.add(address)
    await session.flush()
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="contact.address_changed",
        entity_type="contact",
        entity_id=contact_id,
        actor_user_id=principal.user_id,
        payload={
            "change_request_id": str(row.id),
            "address_id": str(address.id),
            "valid_from": payload["valid_from"],
            "is_primary": due,
            "evidence_document_id": payload.get("document_id"),
            "source": "portal",
        },
    )


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


class MagicLinkRequestIn(_In):
    email: str = Field(min_length=3, max_length=320)
    # Only needed when the request does not reach the API through a host mapped to one tenant
    # (``resolve_host_tenant``); the portal frontend of a mapped domain never sends it.
    tenant_id: uuid.UUID | None = None


class MagicLinkConsumeIn(_In):
    token: str = Field(min_length=10, max_length=200)


class MagicLinkCodeIn(_In):
    tenant_id: uuid.UUID
    link_id: uuid.UUID
    code: str = Field(min_length=6, max_length=8)


class MagicLinkOut(BaseModel):
    """Never carries the link token or the e-mail code (rule 0.1.13); ``code_required`` means
    the account switched on the optional e-mail code second factor (M21-01)."""

    status: str
    link_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    access_token: str | None = None
    token_type: str = "Bearer"  # noqa: S105 - fixed scheme name, not a secret
    expires_in: int | None = None
    refresh_token: str | None = None


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _issued_out(status: str, issued: auth_service.IssuedTokens) -> MagicLinkOut:
    return MagicLinkOut(
        status=status,
        tenant_id=issued.tenant_id,
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token,
    )


@router.post(
    "/magic-link/request", status_code=204, summary="Anmeldelink per E-Mail anfordern (M21-01)"
)
async def magic_link_request(body: MagicLinkRequestIn, request: Request) -> Response:
    """Always answers 204, whether or not the address has a portal account (no enumeration,
    rule 0.1.13); rate limited per address (``magic_link.RATE_LIMIT_PER_HOUR``)."""
    tenant_id = body.tenant_id or await resolve_host_tenant(request)
    if tenant_id is not None:
        settings = _settings(request)
        redis = request.app.state.resources.redis
        portal_url = getattr(settings, "web_portal_url", None)
        async with tenant_transaction(sessions(request), tenant_id) as session:
            await magic_link.request_link(
                session,
                settings,
                redis,
                tenant_id=tenant_id,
                email=body.email,
                portal_url=str(portal_url) if portal_url else None,
            )
    return Response(status_code=204)


@router.post("/magic-link/consume", summary="Anmeldelink einlösen (M21-01)")
async def magic_link_consume(body: MagicLinkConsumeIn, request: Request) -> MagicLinkOut:
    settings = _settings(request)
    redis = request.app.state.resources.redis
    portal_url = getattr(settings, "web_portal_url", None)
    result = await magic_link.consume_link(
        sessions(request),
        settings,
        redis,
        token=body.token,
        user_agent=request.headers.get("user-agent"),
        portal_url=str(portal_url) if portal_url else None,
    )
    if result.status == "code_required":
        tenant_id, _secret = magic_link.parse_token(body.token)
        return MagicLinkOut(status="code_required", link_id=result.link_id, tenant_id=tenant_id)
    assert result.issued is not None  # noqa: S101 - status "ok" always carries issued tokens
    return _issued_out("ok", result.issued)


@router.post("/magic-link/verify-code", summary="Bestätigungscode prüfen, Sitzung ausstellen")
async def magic_link_verify_code(body: MagicLinkCodeIn, request: Request) -> MagicLinkOut:
    issued = await magic_link.verify_code(
        sessions(request),
        _settings(request),
        tenant_id=body.tenant_id,
        link_id=body.link_id,
        code=body.code,
        user_agent=request.headers.get("user-agent"),
    )
    return _issued_out("ok", issued)


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
        permissions = await access.staff_permissions(session, account)
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
            "permissions": sorted(permissions),
        }


@router.get("/notifications", summary="Eigene Benachrichtigungen (Portal)")
async def notifications(
    request: Request, unread: bool = False, ctx: Portal = Depends(portal_user)
) -> list[NotificationOut]:
    """Notifications of the portal user with portal routes as ``href`` (workspace.links)."""
    principal, _account = ctx
    async with tenant_tx(request, principal) as session:
        query = select(Notification).where(Notification.user_id == principal.user_id)
        if unread:
            query = query.where(Notification.read_at.is_(None))
        rows = await session.scalars(query.order_by(Notification.created_at.desc()).limit(50))
        return await notification_out(session, list(rows.all()), portal=True)


@router.post("/notifications/read", status_code=204, summary="Als gelesen markieren (Portal)")
async def notifications_read(
    request: Request, ids: list[uuid.UUID] | None = None, ctx: Portal = Depends(portal_user)
) -> None:
    principal, _account = ctx
    async with tenant_tx(request, principal) as session:
        query = update(Notification).where(
            Notification.user_id == principal.user_id, Notification.read_at.is_(None)
        )
        if ids:
            query = query.where(Notification.id.in_(ids))
        await session.execute(query.values(read_at=datetime.now(UTC)))


@router.get("/documents", summary="Freigegebene Dokumente")
async def documents(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        docs = await access.visible_documents(session, account, local_today())
        notes = await access.redaction_notes(session, {d.id for d in docs})
        return [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "created_at": d.created_at,
                # E06, D31: a released version of a receipt carries the redaction note.
                "redaction_note": notes.get(d.id),
            }
            for d in docs
        ]


@router.get("/documents/{document_id}", summary="Dokument öffnen (Abruf wird als Indiz vermerkt)")
async def open_document(
    document_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Metadata of one released document. Opening writes a read receipt of kind "opened"
    (11.3, D34): an indication only, no delivery and no receipt; the list writes nothing."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        docs = {d.id: d for d in await access.visible_documents(session, account, local_today())}
        document = docs.get(document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        note = (await access.redaction_notes(session, {document.id})).get(document.id)
        await read_receipts.record(session, account, document.id, "opened")
        return {
            "id": document.id,
            "title": document.title,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "size": document.size,
            "created_at": document.created_at,
            "redaction_note": note,
            "read_receipt_note": read_receipts.LEGAL_NOTE,
        }


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
        note = (await access.redaction_notes(session, {document.id})).get(document.id)
        # D34: the download is recorded as an indication only (no delivery, no receipt).
        await read_receipts.record(session, account, document.id, "downloaded")
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
            headers={
                "Content-Disposition": content_disposition("attachment", document.filename),
                "X-Content-Type-Options": "nosniff",
                # Header values are latin-1 on the wire: percent encoded UTF-8 (RFC 8187 style).
                **({"X-Redaction-Note": url_quote(note)} if note else {}),
            },
        )


@router.post("/uploads", status_code=201, summary="Datei hochladen (Foto, Angebot, Rechnung)")
async def upload(
    request: Request, file: UploadFile = File(), ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import check_upload, store_document
    from mhvp.handover.images import (
        ImageSanitizeError,
        output_mime_type,
        sanitize_image,
        supports,
    )

    principal, account = ctx
    data = await file.read()
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip()
    if mime not in PORTAL_UPLOAD_MIME_TYPES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail="Im Portal sind nur Fotos (JPEG, PNG, TIFF, HEIC) und PDF zulässig.",
        )
    check_upload(mime, data, request.app.state.settings.document_max_bytes)
    # A55/A58: photos lose EXIF, GPS and other metadata and are scaled like handover photos
    # (M30-04). HEIC/HEIF from iPhones is decoded with pillow-heif and stored as JPEG (A72);
    # a photo type the sanitizer cannot re-encode is refused rather than stored with its
    # metadata; the original is never kept.
    if mime.startswith("image/"):
        if not supports(mime):
            raise ProblemError(
                ErrorCodes.UPLOAD_REJECTED,
                detail="Dieses Bildformat kann nicht bereinigt werden. Bitte JPEG oder PNG "
                "verwenden.",
            )
        try:
            data = sanitize_image(
                data, mime, max_edge=request.app.state.settings.handover_image_max_edge
            )
        except ImageSanitizeError as exc:
            detail = "Das Bild konnte nicht gelesen werden."
            if output_mime_type(mime) != mime:
                detail = (
                    "Das HEIC-Foto konnte nicht gelesen werden. Bitte das Foto als JPEG "
                    "speichern (iPhone: Einstellungen, Kamera, Formate, Maximale "
                    "Kompatibilität) und erneut hochladen."
                )
            raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail=detail) from exc
        if output_mime_type(mime) != mime:
            # The stored bytes are JPEG now; the name follows so downloads open correctly.
            mime = output_mime_type(mime)
            stem = re.sub(r"\.(heic|heif)$", "", file.filename or "upload", flags=re.IGNORECASE)
            file.filename = f"{stem}.jpg"
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
    from mhvp.documents.models import DocumentLink, LinkRole
    from mhvp.properties.models import Unit
    from mhvp.tickets.models import Priority, Ticket, TicketSource
    from mhvp.tickets.routers import SLA_HOURS

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        attachments = await _own_uploads(session, account, body.document_ids)
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
        # SLA-Uhr auch für Portal-Tickets (review 26.09.2026, H6).
        from mhvp.sla.service import start_clock

        await start_clock(session, principal.tenant_id, ticket.id, ticket.priority)
        for doc in attachments:
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=doc.id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                    role=LinkRole.ATTACHMENT,
                )
            )
        await session.flush()
        return {
            "id": ticket.id,
            "number": ticket.number,
            "status": ticket.status.value,
            "attachments": [_attachment_out(d) for d in attachments],
        }


def _attachment_out(doc: Any) -> dict[str, Any]:
    return {"id": doc.id, "title": doc.title, "filename": doc.filename, "mime_type": doc.mime_type}


async def _own_uploads(
    session: AsyncSession, account: PortalAccount, document_ids: list[uuid.UUID]
) -> list[Any]:
    """A55/A58: only documents this portal account uploaded itself (POST /portal/uploads) may
    be attached; anything else is answered as not found so the portal never learns whether a
    foreign id exists. RLS already hides documents of other tenants."""
    from mhvp.documents.models import Document, DocumentSource

    out: list[Any] = []
    for document_id in dict.fromkeys(document_ids):
        doc = await session.get(Document, document_id)
        if (
            doc is None
            or doc.created_by != account.user_id
            or doc.source is not DocumentSource.PORTAL
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Anhang nicht gefunden.")
        out.append(doc)
    return out


async def entity_attachments(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Documents linked to an entity as attachments, oldest first (A55 ticket photos, A58
    execution photos of a work order)."""
    from mhvp.documents.models import Document, DocumentLink, LinkRole

    rows = (
        await session.scalars(
            select(Document)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == entity_type,
                DocumentLink.entity_id == entity_id,
                DocumentLink.role == LinkRole.ATTACHMENT,
            )
            # Links of one request share a timestamp; the UUID v7 id keeps the given order.
            .order_by(DocumentLink.created_at, DocumentLink.id)
        )
    ).all()
    return [_attachment_out(d) for d in rows]


async def ticket_attachments(session: AsyncSession, ticket_id: uuid.UUID) -> list[dict[str, Any]]:
    """Documents linked to a ticket as attachments (A55). Shared with the CRM ticket detail
    (mhvp.tickets.routers.get_ticket)."""
    return await entity_attachments(session, "ticket", ticket_id)


@router.get("/tickets", summary="Eigene Meldungen mit Verlauf")
async def tickets(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    from mhvp.tickets.models import Ticket, TicketComment

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        staff_perms = await access.staff_permissions(session, account)
        query = select(Ticket).order_by(Ticket.number.desc())
        # Staff with "tickets:read" (M2-08 entschieden) see every ticket of the tenant, not
        # only their own reports.
        if "tickets:read" not in staff_perms:
            query = query.where(Ticket.initiator_contact_id == account.contact_id)
        rows = (await session.scalars(query)).all()
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
                    "attachments": await ticket_attachments(session, t.id),
                    # A58: open or accepted appointment proposals of the orders to this
                    # ticket; the resident accepts one via
                    # POST /portal/work-orders/{id}/appointment-proposals/{pid}/accept.
                    "appointment_proposals": await _ticket_proposals(session, t.id),
                }
            )
        return out


async def _ticket_proposals(session: AsyncSession, ticket_id: uuid.UUID) -> list[dict[str, Any]]:
    from mhvp.tickets.models import WorkOrder, WorkOrderAppointmentProposal

    rows = (
        await session.scalars(
            select(WorkOrderAppointmentProposal)
            .join(WorkOrder, WorkOrder.id == WorkOrderAppointmentProposal.work_order_id)
            .where(
                WorkOrder.ticket_id == ticket_id,
                WorkOrderAppointmentProposal.status.in_(("proposed", "accepted")),
            )
            .order_by(WorkOrderAppointmentProposal.starts_at)
        )
    ).all()
    return [_proposal_out(p) for p in rows]


def _proposal_out(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "work_order_id": p.work_order_id,
        "starts_at": p.starts_at,
        "note": p.note,
        "status": p.status,
        "decided_at": p.decided_at,
    }


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
    payload = dict(body.payload)
    if body.kind == "address":
        payload = _address_payload(payload)
    async with tenant_tx(request, principal) as session:
        if body.kind == "address" and payload.get("document_id"):
            from mhvp.documents.models import Document

            doc = await session.get(Document, uuid.UUID(payload["document_id"]))
            if doc is None or doc.created_by != principal.user_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Der Nachweis muss eine eigene Datei sein."
                )
        return await _propose(session, principal, account, body.kind, payload)


ADDRESS_FIELDS = ("street", "house_number", "postal_code", "city", "addition", "country")


def _address_payload(payload: dict[str, str]) -> dict[str, str]:
    """Validate an address proposal (M21-02): street, postal code, city and the date from
    which the address applies are required; the evidence document is optional."""
    out = {k: (payload.get(k) or "").strip() for k in ADDRESS_FIELDS}
    if not out["street"] or not out["postal_code"] or not out["city"]:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Straße, Postleitzahl und Ort sind erforderlich."
        )
    out["country"] = (out["country"] or "DE").upper()[:2]
    try:
        raw = (payload.get("valid_from") or "").strip()
        out["valid_from"] = date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Bitte angeben, ab wann die Anschrift gilt."
        ) from exc
    document_id = (payload.get("document_id") or "").strip()
    if document_id:
        try:
            out["document_id"] = str(uuid.UUID(document_id))
        except ValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nachweis ungültig.") from exc
    return out


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
    from mhvp.accounting.models import JournalEntry, Ledger, LedgerAccount
    from mhvp.contracts.models import Contract, DebtorAccountReservation

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        contract_ids = (await _scopes(session, account)).get("contract", set())
        items: list[dict[str, Any]] = []
        entry_ids: set[uuid.UUID] = set()
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
                if i["journal_entry_id"]:
                    entry_ids.add(i["journal_entry_id"])
                items.append(
                    {
                        "contract_number": contract.number,
                        "due_date": i["due_date"],
                        "amount": i["amount"],
                        "remaining": i["remaining"],
                        "_journal_entry_id": i["journal_entry_id"],
                    }
                )
        # Stage 4 (M11-finapi): a row carries a document reference only when the booking that
        # created it (`JournalEntry.document_id`, set for a posted invoice, 7.9) is one this
        # account may actually see (`access.visible_documents`, same check the download
        # endpoint re-runs) -- never a bare id the portal could not then open (rule 0.1.3).
        document_by_entry: dict[uuid.UUID, uuid.UUID] = {}
        if entry_ids:
            rows = (
                await session.execute(
                    select(JournalEntry.id, JournalEntry.document_id).where(
                        JournalEntry.id.in_(entry_ids), JournalEntry.document_id.is_not(None)
                    )
                )
            ).all()
            visible = await access.visible_documents(session, account, local_today())
            visible_ids = {d.id for d in visible}
            document_by_entry = {
                entry_id: doc_id for entry_id, doc_id in rows if doc_id in visible_ids
            }
        for item in items:
            entry_id = item.pop("_journal_entry_id")
            item["document_id"] = document_by_entry.get(entry_id)
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


async def _order(session: AsyncSession, o: Any) -> dict[str, Any]:
    from mhvp.tickets.models import WorkOrderAppointmentProposal

    proposals = (
        await session.scalars(
            select(WorkOrderAppointmentProposal)
            .where(WorkOrderAppointmentProposal.work_order_id == o.id)
            .order_by(
                WorkOrderAppointmentProposal.created_at, WorkOrderAppointmentProposal.starts_at
            )
        )
    ).all()
    return {
        "id": o.id,
        "description": o.description,
        "status": o.status.value,
        "quote_amount": o.quote_amount,
        "scheduled_at": o.scheduled_at,
        # A58: every proposal of this order with its status (proposed, accepted, declined,
        # superseded) and the execution photos linked as attachments.
        "appointment_proposals": [_proposal_out(p) for p in proposals],
        "photos": await entity_attachments(session, "work_order", o.id),
    }


@router.get("/work-orders", summary="Eigene Aufträge (Dienstleister)")
async def work_orders(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    from mhvp.tickets.models import WorkOrder

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        staff_perms = await access.staff_permissions(session, account)
        query = select(WorkOrder).order_by(WorkOrder.created_at.desc())
        # Staff with "work_orders:read" (M2-08 entschieden) see every work order of the tenant.
        if "work_orders:read" not in staff_perms:
            query = query.where(WorkOrder.provider_contact_id == account.contact_id)
        rows = await session.scalars(query)
        return [await _order(session, o) for o in rows.all()]


@router.post("/work-orders/{order_id}/decline", summary="Auftrag ablehnen")
async def decline(
    order_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        await _step(session, order, OrderStatus.REJECTED, principal, "abgelehnt")
        return await _order(session, order)


@router.post("/work-orders/{order_id}/quote", summary="Angebot abgeben")
async def quote(
    order_id: uuid.UUID, body: PortalQuoteIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if body.document_id is not None:
            # Review 1.22 Nr. 16: the quote document must be an own upload, like photos.
            await _own_uploads(session, account, [body.document_id])
        await _step(session, order, OrderStatus.QUOTED, principal, "Angebot")
        order.quote_amount, order.quote_document_id = body.amount, body.document_id
        return await _order(session, order)


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
        return await _order(session, order)


@router.post("/work-orders/{order_id}/complete", summary="Ausführung dokumentieren")
async def complete(
    order_id: uuid.UUID,
    body: PortalCompleteIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.documents.models import DocumentLink, LinkRole
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        photos = await _own_uploads(
            session, account, [*body.document_ids, *body.photo_document_ids]
        )
        if order.status is OrderStatus.SCHEDULED:
            await _step(session, order, OrderStatus.IN_PROGRESS, principal, "Beginn")
        await _step(session, order, OrderStatus.DONE, principal, "ausgeführt")
        order.completion_report = body.report
        order.photo_document_ids = [d.id for d in photos]
        for doc in photos:
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=doc.id,
                    entity_type="work_order",
                    entity_id=order.id,
                    role=LinkRole.ATTACHMENT,
                )
            )
        await session.flush()
        return await _order(session, order)


# Appointment proposals (A58) ------------------------------------------------------------


async def _resident_scope(session: AsyncSession, account: PortalAccount, order: Any) -> bool:
    """True when this portal account is the resident affected by the order: the initiator of
    the order's ticket or an occupant (grant on the unit) of the ticket's unit."""
    from mhvp.tickets.models import Ticket

    if order.ticket_id is None:
        return False
    ticket = await session.get(Ticket, order.ticket_id)
    if ticket is None:
        return False
    if ticket.initiator_contact_id == account.contact_id:
        return True
    if ticket.unit_id is None:
        return False
    scopes = await _scopes(session, account)
    return ticket.unit_id in scopes.get("unit", set())


@router.post(
    "/work-orders/{order_id}/appointment-proposals",
    status_code=201,
    summary="Terminvorschläge an den Bewohner (bis zu drei, nach Freigabe)",
)
async def propose_appointments(
    order_id: uuid.UUID,
    body: PortalProposalsIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> list[dict[str, Any]]:
    from mhvp.tickets.models import OrderStatus, ProposalStatus, WorkOrderAppointmentProposal

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if order.status not in (OrderStatus.APPROVED, OrderStatus.SCHEDULED):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Terminvorschläge sind erst nach Freigabe des Auftrags möglich.",
            )
        if order.ticket_id is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Auftrag hat keine Meldung, an die ein Bewohner gebunden ist.",
            )
        if len({p.starts_at for p in body.proposals}) != len(body.proposals):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Terminvorschläge sind doppelt.")
        open_rows = (
            await session.scalars(
                select(WorkOrderAppointmentProposal).where(
                    WorkOrderAppointmentProposal.work_order_id == order.id,
                    WorkOrderAppointmentProposal.status == ProposalStatus.PROPOSED.value,
                )
            )
        ).all()
        for old in open_rows:
            old.status = ProposalStatus.SUPERSEDED.value
        rows = [
            WorkOrderAppointmentProposal(
                tenant_id=principal.tenant_id,
                work_order_id=order.id,
                starts_at=p.starts_at,
                note=p.note,
                proposed_by_contact_id=account.contact_id,
                created_by=principal.user_id,
            )
            for p in body.proposals
        ]
        session.add_all(rows)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="work_order.appointment_proposed",
            entity_type="work_order",
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={
                "ticket_id": str(order.ticket_id),
                "proposal_ids": [str(r.id) for r in rows],
                "starts_at": [r.starts_at.isoformat() for r in rows],
            },
        )
        return [_proposal_out(r) for r in rows]


@router.get(
    "/work-orders/{order_id}/appointment-proposals",
    summary="Terminvorschläge zum Auftrag (Dienstleister oder betroffener Bewohner)",
)
async def appointment_proposals(
    order_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    from mhvp.tickets.models import WorkOrder, WorkOrderAppointmentProposal

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id)
        if order is None or (
            order.provider_contact_id != account.contact_id
            and not await _resident_scope(session, account, order)
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = (
            await session.scalars(
                select(WorkOrderAppointmentProposal)
                .where(WorkOrderAppointmentProposal.work_order_id == order.id)
                .order_by(WorkOrderAppointmentProposal.starts_at)
            )
        ).all()
        return [_proposal_out(p) for p in rows]


@router.post(
    "/work-orders/{order_id}/appointment-proposals/{proposal_id}/accept",
    summary="Terminvorschlag annehmen (betroffener Bewohner)",
)
async def accept_appointment(
    order_id: uuid.UUID,
    proposal_id: uuid.UUID,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.tickets.models import (
        OrderStatus,
        ProposalStatus,
        TicketComment,
        WorkOrder,
        WorkOrderAppointmentProposal,
        WorkOrderEvent,
    )

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await session.get(WorkOrder, order_id, with_for_update=True)
        # Only the affected resident confirms; the provider and everyone else get not found.
        if order is None or not await _resident_scope(session, account, order):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        proposal = await session.get(WorkOrderAppointmentProposal, proposal_id)
        if proposal is None or proposal.work_order_id != order.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if proposal.status != ProposalStatus.PROPOSED.value:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Dieser Terminvorschlag ist nicht mehr offen."
            )
        if order.status not in (OrderStatus.APPROVED, OrderStatus.SCHEDULED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Auftrag ist nicht mehr in der Terminplanung."
            )
        now = datetime.now(UTC)
        siblings = (
            await session.scalars(
                select(WorkOrderAppointmentProposal).where(
                    WorkOrderAppointmentProposal.work_order_id == order.id,
                    WorkOrderAppointmentProposal.status == ProposalStatus.PROPOSED.value,
                    WorkOrderAppointmentProposal.id != proposal.id,
                )
            )
        ).all()
        for other in siblings:
            other.status = ProposalStatus.DECLINED.value
            other.decided_by_contact_id = account.contact_id
            other.decided_at = now
        proposal.status = ProposalStatus.ACCEPTED.value
        proposal.decided_by_contact_id = account.contact_id
        proposal.decided_at = now
        if order.status is OrderStatus.APPROVED:
            await _step(session, order, OrderStatus.SCHEDULED, principal, "Termin bestätigt")
        else:
            session.add(
                WorkOrderEvent(
                    tenant_id=order.tenant_id,
                    work_order_id=order.id,
                    from_status=order.status.value,
                    to_status=order.status.value,
                    user_id=principal.user_id,
                    note="Portal: Termin bestätigt (neuer Vorschlag)",
                )
            )
        order.scheduled_at = proposal.starts_at
        when = proposal.starts_at.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y %H:%M")
        session.add(
            TicketComment(
                tenant_id=principal.tenant_id,
                ticket_id=order.ticket_id,
                internal=False,
                author_contact_id=account.contact_id,
                body=f"Termin bestätigt: {when} Uhr",
            )
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="work_order.appointment_confirmed",
            entity_type="work_order",
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={
                "ticket_id": str(order.ticket_id),
                "proposal_id": str(proposal.id),
                "scheduled_at": proposal.starts_at.isoformat(),
            },
        )
        await session.flush()
        return {
            "order": await _order(session, order),
            "proposal": _proposal_out(proposal),
        }


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
