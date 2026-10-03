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

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth import service as auth_service
from mhvp.core.auth.portal_roles import PortalRelations, derive_portal_roles
from mhvp.core.auth.principal import (
    TenantPrincipal,
    get_principal,
    require_permission,
    resolve_host_tenant,
    sessions,
    tenant_tx,
)
from mhvp.core.auth.scope import allowed_property_ids
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_limited
from mhvp.documents import payment_files
from mhvp.portal import access, magic_link, public_terms, read_receipts
from mhvp.portal.models import AccessGrant, ChangeRequest, PortalAccount
from mhvp.portal.property_scope import (
    contact_visible,
    ensure_contact_visible,
    portal_admin_guard,
)
from mhvp.portal.public_terms import PortalPublicTermsOut
from mhvp.portal.status import LOGIN_STATUSES, target_status, user_locked
from mhvp.tickets.order_events import emit_completed_if_done
from mhvp.workspace.models import Notification
from mhvp.workspace.routers import NotificationOut, notification_out
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(
    prefix="/portal-admin",
    tags=["Portal Verwaltung"],
    dependencies=[Depends(portal_admin_guard)],  # M2-02, R08-01
)
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
    # AB08 (6.2): false creates the account as not_invited; a later POST for the same contact
    # sends the invitation (status invited).
    send_invitation: bool = True


class PortalAcceptIn(_In):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    # AC06: once the tenant has published a terms version (consent policy), activation needs
    # the acceptance of exactly that version; it is stored as a portal_terms consent.
    accept_terms: bool | None = None
    terms_version: str | None = Field(default=None, min_length=1, max_length=60)


class PortalTicketIn(_In):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=20000)
    unit_id: uuid.UUID | None = None
    # M21-03: where the damage is (room, building part, floor); free text, part of the public
    # description of the ticket. No geo coordinates are collected (data minimisation).
    location: str | None = Field(default=None, max_length=200)
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
    # AM06 (GAJ-401, section 14 "Zählerstand mit Foto melden"): photos of the meter uploaded
    # by this account via POST /portal/uploads; linked to the proposal as attachments
    # (entity_type "portal_change_request") and, on acceptance, to the meter reading.
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


# AM06/AN02 (GAJ-401): the reading photo is expected (section 14). The tenant switch
# ``portal_feature_setting.meter_photo_mode`` (migration 0451) decides: off, hint (default,
# ``photo_missing`` flag and note, the reading still reaches the review) or required (422).
# Decision AM06-01 stays open; the default keeps the behaviour before 0451.
METER_PHOTO_REQUIRED_DEFAULT = True
METER_PHOTO_MISSING_NOTE = (
    "Ohne Foto des Zählerstands kann die Verwaltung die Ablesung nur eingeschränkt prüfen. "
    "Bitte reichen Sie ein Foto nach oder melden Sie den Stand erneut mit Foto."
)


class PortalDecideIn(_In):
    accept: bool
    note: str | None = Field(default=None, max_length=2000)


class PortalQuoteIn(_In):
    amount: Decimal = Field(gt=0)
    document_id: uuid.UUID | None = None


class PortalDeclineIn(_In):
    reason: str | None = Field(default=None, max_length=1000)


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
    gross: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    # M22-02: optional breakdown as printed on the invoice; transferred into the receipt draft.
    net: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    vat_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    iban: str | None = Field(default=None, max_length=42)
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
    invite: bool = True,
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
        existing = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == contact_id)
        )
        if existing is not None:
            # T13-01: only a lapsed, never accepted invitation is issued again (new token,
            # new expiry); an active, locked or still valid invitation stays a conflict.
            now = datetime.now(UTC)
            if (
                existing.status == "invited"
                and existing.invitation_expires_at is not None
                and existing.invitation_expires_at <= now
            ) or existing.status in ("expired", "not_invited"):
                secret = secrets.token_urlsafe(32)
                existing.invitation_hash = _hash(secret)
                existing.invitation_expires_at = now + timedelta(days=INVITE_DAYS)
                existing.invited_at = now
                existing.status = "invited"  # 6.2: expired or not_invited -> invited
                grants = await access.sync_grants(session, existing)
                await emit(
                    session,
                    tenant_id=principal.tenant_id,
                    type="portal_account.invitation_reissued",
                    entity_type="portal_account",
                    entity_id=existing.id,
                    actor_user_id=principal.user_id,
                    payload={"grants": grants},
                )
                token = f"{principal.tenant_id.hex}.{secret}"
                return {
                    "id": existing.id,
                    "user_id": existing.user_id,
                    "grants": grants,
                    "invitation_token": token,
                    "invitation_url": invitation_url(request, token),
                    "reissued": True,
                }
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
            status="invited" if invite else "not_invited",
            invitation_hash=_hash(secret) if invite else None,
            invitation_expires_at=(
                datetime.now(UTC) + timedelta(days=INVITE_DAYS) if invite else None
            ),
            invited_at=datetime.now(UTC) if invite else None,
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
        invite_token = f"{principal.tenant_id.hex}.{secret}" if invite else None
        return {
            "id": account.id,
            "user_id": user_id,
            "grants": grants,
            "invitation_token": invite_token,
            # A56: link to the portal's invitation page (shown as text and QR in the CRM); None
            # when no public portal URL is configured.
            "invitation_url": invitation_url(request, invite_token) if invite_token else None,
        }


_user_locked = user_locked


def effective_account_status(account: PortalAccount, user: Any, now: datetime) -> str:
    """GA02-07 (6.2): the status is stored (``mhvp.portal.status``, beat job); between two job
    runs the read applies the same rule, so the list never shows a stale value."""
    return target_status(account, user, now)


class PortalAccountOut(BaseModel):
    """Portal account of a contact as the CRM sees it (A86). Never carries the invitation
    hash, a password hash or a token; ``status`` is the account status of the model
    (``invited`` until the invitation is accepted, then ``active``), ``locked`` mirrors a
    temporary login lock of the platform user."""

    id: uuid.UUID
    contact_id: uuid.UUID
    email: str
    status: str
    roles: list[str]
    locked: bool
    invited_at: datetime
    invitation_expires_at: datetime | None
    activated_at: datetime | None
    last_login_at: datetime | None
    # M21-01: optional e-mail code second factor on top of the magic link login.
    magic_link_2fa: bool


@admin.get(
    "/accounts", summary="Portalzugänge eines Kontakts", dependencies=[Depends(strict_query)]
)
async def list_accounts(
    contact_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("contacts:read")),
) -> list[PortalAccountOut]:
    """Portal accounts of one contact of the own tenant (RLS); an unknown or foreign contact
    yields an empty list, never 404, so the CRM can show "kein Zugang" without a probe."""
    from mhvp.platform.models import User

    async with tenant_tx(request, principal) as session:
        if not await contact_visible(session, contact_id):  # M2-02, R08-01
            return []
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
                status=effective_account_status(account, user, now),
                roles=list(account.roles or []),
                locked=_user_locked(user, now),
                invited_at=account.invited_at or account.created_at,
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
    if allowed_property_ids(principal) is not None:  # M2-02, R08-01: contract of the contact
        async with tenant_tx(request, principal) as session:
            await ensure_contact_visible(session, body.contact_id)
    return await provision_account(
        request,
        principal,
        contact_id=body.contact_id,
        email=body.email,
        display_name=body.display_name,
        invite=body.send_invitation,
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


class DocumentClassGrantIn(_In):
    legal_entity_id: uuid.UUID
    document_class: str = Field(min_length=1, max_length=63)
    role: str = Field(pattern="^(tenant|owner|board|provider)$")
    valid_from: date | None = None
    valid_to: date | None = None


class DocumentClassGrantOut(_In):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    document_class: str
    role: str
    valid_from: date
    valid_to: date | None


@admin.get(
    "/accounts/{account_id}/document-class-grants",
    summary="Freigaben je Unterlagenklasse",
    response_model=list[DocumentClassGrantOut],
    dependencies=[Depends(strict_query)],
)
async def list_document_class_grants(
    account_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> list[DocumentClassGrantOut]:
    async with tenant_tx(request, principal) as session:
        if await session.get(PortalAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(AccessGrant).where(
                AccessGrant.account_id == account_id, AccessGrant.scope_type == "document_class"
            )
        )
        return [
            DocumentClassGrantOut(
                id=g.id,
                legal_entity_id=g.scope_id,
                document_class=str(g.document_class),
                role=g.role,
                valid_from=g.valid_from,
                valid_to=g.valid_to,
            )
            for g in rows
        ]


@admin.post(
    "/accounts/{account_id}/document-class-grants",
    status_code=201,
    summary="Unterlagenklasse freigeben (6.9.6)",
    response_model=DocumentClassGrantOut,
)
async def add_document_class_grant(
    account_id: uuid.UUID,
    body: DocumentClassGrantIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> DocumentClassGrantOut:
    """GA03-05: releases the documents of one class of a legal entity (e.g. statement vouchers
    for the advisory board). The class must exist as a retention profile class."""
    from mhvp.documents.models import RetentionProfile
    from mhvp.properties.models import LegalEntity

    async with tenant_tx(request, principal) as session:
        if await session.get(PortalAccount, account_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if await session.get(LegalEntity, body.legal_entity_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        known = await session.scalar(
            select(RetentionProfile.id)
            .where(RetentionProfile.document_class == body.document_class)
            .limit(1)
        )
        if known is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Unterlagenklasse unbekannt.")
        start = body.valid_from or local_today()
        if body.valid_to is not None and body.valid_to < start:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Gültigkeitsende vor Beginn.")
        grant = AccessGrant(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            account_id=account_id,
            scope_type="document_class",
            scope_id=body.legal_entity_id,
            document_class=body.document_class,
            right="read",
            legal_basis="document_class_grant",
            role=body.role,
            valid_from=start,
            valid_to=body.valid_to,
        )
        session.add(grant)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_account.document_class_grant_created",
            entity_type="portal_account",
            entity_id=account_id,
            actor_user_id=principal.user_id,
            payload={"legal_entity_id": str(body.legal_entity_id), "class": body.document_class},
        )
        return DocumentClassGrantOut(
            id=grant.id,
            legal_entity_id=body.legal_entity_id,
            document_class=body.document_class,
            role=body.role,
            valid_from=start,
            valid_to=body.valid_to,
        )


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
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_account.security_changed",
            entity_type="portal_account",
            entity_id=account_id,
            actor_user_id=principal.user_id,
            payload={"magic_link_2fa": body.magic_link_2fa},
        )
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
        account.invited_at = datetime.now(UTC)
        if account.status in ("not_invited", "expired"):
            account.status = "invited"  # 6.2: the letter is the invitation
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


@admin.get(
    "/change-requests", summary="Vorschläge aus dem Portal", dependencies=[Depends(strict_query)]
)
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
        rows = (
            await session.execute(query.order_by(ChangeRequest.created_at.desc()).limit(500))
        ).all()
        # U15 (M2-02): with a property assignment only requests of visible contacts.
        visible: dict[uuid.UUID, bool] = {}
        for _r, cid in rows:
            if cid not in visible:
                visible[cid] = await contact_visible(session, cid)
        rows = [row for row in rows if visible[row[1]]]
        # Accepted invoice submissions point to their receipt draft (M22-02, Q11).
        from mhvp.receipts.models import ReceiptDraft

        document_ids: list[uuid.UUID] = []
        for r, _cid in rows:
            if r.kind == "invoice_submission" and r.status == "accepted":
                try:
                    document_ids.append(uuid.UUID(json.loads(r.payload)["document_id"]))
                except (KeyError, ValueError, TypeError):
                    continue
        drafts: dict[uuid.UUID, uuid.UUID] = {}
        if document_ids:
            draft_rows = await session.execute(
                select(ReceiptDraft.document_id, ReceiptDraft.id).where(
                    ReceiptDraft.document_id.in_(document_ids), ReceiptDraft.source == "portal"
                )
            )
            drafts = {doc_id: draft_id for doc_id, draft_id in draft_rows.all()}  # noqa: C416

        def _draft_id(r: ChangeRequest) -> uuid.UUID | None:
            if r.kind != "invoice_submission":
                return None
            try:
                return drafts.get(uuid.UUID(json.loads(r.payload)["document_id"]))
            except (KeyError, ValueError, TypeError):
                return None

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
                "receipt_draft_id": _draft_id(r),
            }
            for r, cid in rows
        ]


# Contact master data fields a portal change request of this kind touches (GAC-08).
_PORTAL_CONTACT_FIELDS = {
    "email": "emails",
    "phone": "phones",
    "bank_account": "bank_accounts",
    "address": "addresses",
}


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
        account = await session.get(PortalAccount, row.account_id)
        if account is not None:
            await ensure_contact_visible(session, account.contact_id)  # U15, M2-02
        if row.status != "proposed":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits entschieden.")
        payload = json.loads(row.payload)
        receipt_draft_id: uuid.UUID | None = None
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
                reading = MeterReading(
                    tenant_id=row.tenant_id,
                    meter_id=uuid.UUID(payload["meter_id"]),
                    value=Decimal(payload["value"]),
                    read_at=date.fromisoformat(payload["read_at"]),
                    source=ReadingSource.PORTAL,
                )
                session.add(reading)
                if payload.get("document_ids"):
                    # AM06 (GAJ-401): the reading photo stays the evidence of the reading.
                    from mhvp.documents.models import DocumentLink, LinkRole

                    await session.flush()
                    for doc_id in payload["document_ids"]:
                        session.add(
                            DocumentLink(
                                tenant_id=row.tenant_id,
                                document_id=uuid.UUID(doc_id),
                                entity_type="meter_reading",
                                entity_id=reading.id,
                                role=LinkRole.ATTACHMENT,
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
            elif row.kind == "invoice_submission":
                # M22-02: the accepted submission becomes a receipt draft (Belegeingang),
                # never a posting; the order moves to invoiced.
                receipt_draft_id = await _apply_invoice_submission(session, principal, row, payload)
            changed_field = _PORTAL_CONTACT_FIELDS.get(row.kind)
            if changed_field is not None:
                # GAC-08: subscribers of contact.updated (smart-einzug, lexoffice mirror) also
                # learn about an accepted portal change; field names only, never the values.
                await emit(
                    session,
                    tenant_id=row.tenant_id,
                    type="contact.updated",
                    entity_type="contact",
                    entity_id=account.contact_id,
                    actor_user_id=principal.user_id,
                    payload={
                        "fields": [changed_field],
                        "source": "portal",
                        "change_request_id": str(row.id),
                    },
                )
        row.status, row.decided_by, row.decision_note = (
            ("accepted" if body.accept else "rejected"),
            principal.user_id,
            body.note,
        )
        await session.flush()
        result: dict[str, Any] = {"id": row.id, "status": row.status}
        if receipt_draft_id is not None:
            result["receipt_draft_id"] = receipt_draft_id
        return result


def _invoice_breakdown(body: PortalInvoiceSubmitIn) -> dict[str, Any]:
    """M22-02: validates the optional net, VAT rate and IBAN of a submission and returns the
    normalised values (``net``, ``vat``, ``vat_rate``, ``iban``). Net plus VAT must equal the
    gross amount (cent tolerance of one for a rate given); the rate is the provider's entry,
    no tax classification is derived here."""
    from mhvp.contacts.validation import InvalidValueError, normalise_iban

    cent = Decimal("0.01")
    out: dict[str, Any] = {}
    net = body.net
    if net is None and body.vat_rate is not None:
        net = (body.gross / (1 + body.vat_rate / 100)).quantize(cent)
    if net is not None:
        if net > body.gross:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Netto darf nicht über dem Brutto liegen."
            )
        vat = body.gross - net
        if body.vat_rate is not None and body.net is not None:
            expected = (net * body.vat_rate / 100).quantize(cent)
            if abs(expected - vat) > cent:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Netto, USt-Satz und Brutto passen nicht zusammen.",
                )
        out.update(net=str(net), vat=str(vat))
        if body.vat_rate is not None:
            out["vat_rate"] = str(body.vat_rate)
    if body.iban:
        try:
            out["iban"] = normalise_iban(body.iban)
        except InvalidValueError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    return out


async def _apply_invoice_submission(
    session: AsyncSession, principal: TenantPrincipal, row: ChangeRequest, payload: dict[str, Any]
) -> uuid.UUID:
    """M22-02: takes an accepted invoice submission of a provider into the Belegeingang as a
    receipt draft (status proposed, source ``portal``) with the values the provider entered,
    and sets the work order to ``invoiced``. The draft is reviewed and confirmed in the
    Belegeingang like any other (M14); nothing is posted or paid here, and the release of
    posting stays behind gate G1. Idempotent per document: an existing draft is reused."""
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import Property
    from mhvp.receipts.models import ReceiptDraft, ReceiptDraftStatus
    from mhvp.tickets.models import OrderStatus, WorkOrder, WorkOrderEvent

    if not principal.has("accounting:create"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Für die Übernahme in den Belegeingang fehlt die Berechtigung Buchhaltung.",
            developer_message="Missing accounting:create.",
        )
    order = await session.get(WorkOrder, uuid.UUID(payload["work_order_id"]), with_for_update=True)
    if order is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Auftrag nicht gefunden.")
    document_id = uuid.UUID(payload["document_id"])
    existing = await session.scalar(
        select(ReceiptDraft.id).where(
            ReceiptDraft.document_id == document_id, ReceiptDraft.source == "portal"
        )
    )
    if existing is not None:
        draft_id: uuid.UUID = existing
    else:
        provider = await session.get(Contact, order.provider_contact_id)
        prop = await session.get(Property, order.property_id)

        def _entered(value: Any, note: str) -> dict[str, Any]:
            # Values typed by the provider: no AI confidence, marked as entered in the portal.
            return {"value": value, "confidence": 1.0, "source": "local", "note": note}

        note = "Vom Dienstleister im Portal eingegeben"
        fields: dict[str, Any] = {
            "supplier_name": _entered(provider.display_name if provider else None, note),
            "invoice_number": _entered(str(payload["number"]).strip(), note),
            "invoice_date": _entered(payload["invoice_date"], note),
            "gross": _entered(str(payload["gross"]), note),
            "currency": _entered("EUR", note),
            "property_ref": _entered(prop.number if prop else None, "Objekt des Auftrags"),
        }
        warnings = [
            "Die Angaben stammen vom Dienstleister aus dem Portal und sind mit dem Beleg "
            "abzugleichen."
        ]
        if payload.get("net") is not None:
            rate = payload.get("vat_rate")
            fields["net"] = _entered(str(payload["net"]), note)
            fields["vat"] = _entered(
                str(payload["vat"]), note + (f", USt-Satz {rate} %" if rate else "")
            )
        findings, iban_candidates = await _invoice_findings(
            session, order, provider, payload, document_id
        )
        draft = ReceiptDraft(
            tenant_id=row.tenant_id,
            created_by=principal.user_id,
            document_id=document_id,
            source="portal",
            findings=findings,
            iban_candidates=json.dumps(iban_candidates) if iban_candidates else None,
            status=ReceiptDraftStatus.PROPOSED.value,
            fields=fields,
            property_suggestions=(
                [
                    {
                        "property_id": str(prop.id),
                        "number": prop.number,
                        "name": prop.name,
                        "score": 1.0,
                        "reason": "Objekt des Auftrags",
                    }
                ]
                if prop
                else []
            ),
            warnings=warnings,
        )
        session.add(draft)
        await session.flush()
        draft_id = draft.id
    if order.status is OrderStatus.DONE:
        session.add(
            WorkOrderEvent(
                tenant_id=order.tenant_id,
                work_order_id=order.id,
                from_status=order.status.value,
                to_status=OrderStatus.INVOICED.value,
                user_id=principal.user_id,
                note="Rechnungseinreichung angenommen, Belegentwurf angelegt",
            )
        )
        order.status = OrderStatus.INVOICED
    return draft_id


async def _invoice_findings(
    session: AsyncSession,
    order: Any,
    provider: Any,
    payload: dict[str, Any],
    document_id: uuid.UUID,
) -> tuple[list[str], list[str]]:
    """M22-02: findings for the receipt draft of a portal submission. They only mark, nothing
    is blocked: (1) the IBAN entered is compared with the current accounts of the creditor
    master data (fingerprint, no decryption), (2) the Rechnungsbuch is searched for the same
    issuer with the same number or the same date and gross amount. Returns the findings and
    the IBAN candidates for the draft (stored encrypted, exposed masked)."""
    from mhvp.accounting.models import Invoice
    from mhvp.contacts.models import ContactBankAccount
    from mhvp.core import crypto

    findings: list[str] = []
    candidates: list[str] = []
    iban = payload.get("iban")
    if iban:
        candidates.append(iban)
        accounts = (
            await session.scalars(
                select(ContactBankAccount).where(
                    ContactBankAccount.contact_id == order.provider_contact_id,
                    (ContactBankAccount.valid_to.is_(None))
                    | (ContactBankAccount.valid_to >= local_today()),
                )
            )
        ).all()
        if not accounts:
            findings.append(
                "IBAN-Abgleich: Im Kreditorenstamm ist keine gültige Bankverbindung des "
                f"Dienstleisters hinterlegt (Rechnung: ... {iban[-4:]}); Prüfung vor Zahlung nötig."
            )
        elif crypto.fingerprint(iban) in {a.iban_fingerprint for a in accounts}:
            findings.append(
                "IBAN-Abgleich: Die IBAN der Rechnung stimmt mit dem Kreditorenstamm überein."
            )
        else:
            known = ", ".join(f"... {a.iban_suffix}" for a in accounts)
            findings.append(
                f"IBAN-Abweichung: Die IBAN der Rechnung (... {iban[-4:]}) weicht vom "
                f"Kreditorenstamm ab ({known}); Rückfrage beim Dienstleister vor Zahlung, "
                "Änderung nur über den Vier-Augen-Weg."
            )
    number = str(payload["number"]).strip().lower()
    gross = Decimal(str(payload["gross"]))
    booked = (
        await session.execute(
            select(Invoice.number, Invoice.invoice_date, Invoice.gross).where(
                Invoice.provider_contact_id == order.provider_contact_id,
                (func.lower(Invoice.number) == number)
                | (
                    (Invoice.gross == gross)
                    & (Invoice.invoice_date == date.fromisoformat(str(payload["invoice_date"])))
                ),
            )
        )
    ).all()
    for b_number, b_date, b_gross in booked:
        findings.append(
            f"Mögliches Duplikat: Das Rechnungsbuch enthält vom selben Aussteller Rechnung "
            f"{b_number} vom {b_date.strftime('%d.%m.%Y')} über {b_gross} EUR."
        )
    return findings, candidates


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
    closed_ids: list[str] = []
    backfilled_ids: list[str] = []
    if due:
        from mhvp.contacts import address_history

        if await address_history.is_enabled(session):
            # AO09 (AN05): the former primary address is closed as history, not just demoted.
            now = datetime.now(UTC)
            for old in (
                await session.scalars(
                    select(ContactAddress).where(
                        ContactAddress.contact_id == contact_id,
                        ContactAddress.is_primary.is_(True),
                    )
                )
            ).all():
                if address_history.close_row(old, valid_from - timedelta(days=1), now):
                    backfilled_ids.append(str(old.id))
                closed_ids.append(str(old.id))
            await session.flush()
        else:
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
            **(
                {"closed_address_ids": closed_ids, "valid_from_backfilled_ids": backfilled_ids}
                if closed_ids
                else {}
            ),
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
            or account.status != "invited"
            or account.invitation_expires_at is None
            or account.invitation_expires_at < datetime.now(UTC)
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Einladung ungültig oder abgelaufen.")
        await _accept_portal_terms(
            session, tenant_id, account, bool(body.accept_terms), body.terms_version, request
        )
        account.status, account.activated_at, account.invitation_hash = (
            "active",
            datetime.now(UTC),
            None,
        )
        user_id = account.user_id
        await emit(
            session,
            tenant_id=tenant_id,
            type="portal_account.activated",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=user_id,
            payload={"account_id": str(account.id)},
        )
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
    # M2-04: status "mfa_required" (step token for /auth/mfa/verify) or "mfa_setup_required"
    # (setup token for /auth/mfa/setup/start and /confirm); the tenant policy covers the user.
    mfa_token: str | None = None
    mfa_setup_token: str | None = None


def _step_out(status: str, step_token: str | None, tenant_id: uuid.UUID) -> MagicLinkOut:
    if status == "mfa_required":
        return MagicLinkOut(status=status, tenant_id=tenant_id, mfa_token=step_token)
    return MagicLinkOut(status=status, tenant_id=tenant_id, mfa_setup_token=step_token)


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
    if result.status in ("mfa_required", "mfa_setup_required"):
        tenant_id, _secret = magic_link.parse_token(body.token)
        return _step_out(result.status, result.step_token, tenant_id)
    assert result.issued is not None  # noqa: S101 - status "ok" always carries issued tokens
    return _issued_out("ok", result.issued)


@router.post("/magic-link/verify-code", summary="Bestätigungscode prüfen, Sitzung ausstellen")
async def magic_link_verify_code(body: MagicLinkCodeIn, request: Request) -> MagicLinkOut:
    result = await magic_link.verify_code_step(
        sessions(request),
        _settings(request),
        tenant_id=body.tenant_id,
        link_id=body.link_id,
        code=body.code,
        user_agent=request.headers.get("user-agent"),
    )
    if result.issued is None:
        return _step_out(result.status, result.step_token, body.tenant_id)
    return _issued_out("ok", result.issued)


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
                PortalAccount.user_id == principal.user_id,
                PortalAccount.status.in_(LOGIN_STATUSES),
            )
        )
        if account is not None:
            from mhvp.contacts.consent_rules import portal_terms_decision

            decision = await portal_terms_decision(session, account.contact_id)
            if not decision.allowed:
                raise ProblemError(ErrorCodes.CONTACT_PORTAL_TERMS_MISSING)
    if account is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No active portal account.")
    return tp, account


async def _accept_portal_terms(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    account: PortalAccount,
    accept_terms: bool,
    terms_version: str | None,
    request: Request | None = None,
) -> None:
    """AC06: without published terms nothing is recorded (no invented legal text). With a
    published version the acceptance must name that version. AE34: the acceptance in text form
    is recorded with time, accepted version and a keyed hash of the client address (never the
    address itself)."""
    from mhvp.contacts import consent_rules
    from mhvp.contacts.models import Consent, ConsentKind

    policy = await consent_rules.load_policy(session)
    version = policy.portal_terms_version
    if version is None:
        return
    if not accept_terms or terms_version != version:
        raise ProblemError(
            ErrorCodes.CONTACT_PORTAL_TERMS_MISSING,
            detail=f"Bitte die Nutzungsbedingungen in der Fassung {version} annehmen.",
        )
    now = datetime.now(UTC)
    consent = Consent(
        tenant_id=tenant_id,
        contact_id=account.contact_id,
        kind=ConsentKind.PORTAL_TERMS,
        granted_at=now,
        source=consent_rules.terms_source(version),
        text_version=version,
        ip_hash=_client_hash(request, tenant_id),
    )
    session.add(consent)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="consent.granted",
        entity_type="contact",
        entity_id=account.contact_id,
        actor_user_id=account.user_id,
        payload={
            "kind": "portal_terms",
            "source": consent.source,
            "version": version,
            "declaration_form": "textform",
            "client_evidence": consent.ip_hash is not None,
        },
    )


def _client_hash(request: Request | None, tenant_id: uuid.UUID) -> str | None:
    """Keyed hash (HMAC-SHA256, tenant scoped key) of the client address as acceptance
    evidence. ``None`` without a request, an address or a configured master key; the clear
    address is never stored."""
    if request is None:
        return None
    from mhvp.core import crypto
    from mhvp.core.request_identity import settings_client_ip

    settings = _settings(request)
    address = settings_client_ip(request.scope, settings)
    if address == "unknown":
        return None
    try:
        return crypto.fingerprint(address, scope=f"tenant:{tenant_id.hex}:portal-terms-client")
    except crypto.CryptoError:
        return None


Portal = tuple[TenantPrincipal, PortalAccount]


class PortalTermsAcceptIn(_In):
    accept_terms: bool
    terms_version: str = Field(min_length=1, max_length=60)


@router.get(
    "/public/terms",
    summary="Veröffentlichte Fassung der Nutzungsbedingungen (öffentlich, AE34)",
    dependencies=[Depends(strict_query)],
)
async def portal_public_terms(
    request: Request,
    response: Response,
    tenant: str | None = Query(default=None, max_length=64),
) -> PortalPublicTermsOut:
    """Unauthenticated, for the activation screen before the account exists. Returns only the
    published version; unknown, inactive and not publishing tenants answer the same 404."""
    response.headers["Cache-Control"] = "no-store"
    return await public_terms.published_terms(request, tenant)


@router.get("/terms", summary="Stand der Nutzungsbedingungen des Portals")
async def portal_terms_status(request: Request) -> dict[str, Any]:
    """AC06: published terms version and whether the signed in account has accepted it.
    Reachable without accepted terms so that the portal can ask for the acceptance."""
    tp, account = await _terms_account(request)
    from mhvp.contacts import consent_rules

    async with tenant_tx(request, tp) as session:
        policy = await consent_rules.load_policy(session)
        decision = await consent_rules.portal_terms_decision(session, account.contact_id, policy)
    return {
        "terms_version": policy.portal_terms_version,
        "accepted": decision.allowed,
        "reason": decision.reason,
    }


class PortalTermsAcceptOut(BaseModel):
    """Response of the terms acceptance (GAI-304)."""

    model_config = ConfigDict(extra="allow")
    terms_version: str
    accepted: bool


@router.post(
    "/terms/accept",
    summary="Nutzungsbedingungen des Portals annehmen",
    response_model=PortalTermsAcceptOut,
)
async def portal_terms_accept(body: PortalTermsAcceptIn, request: Request) -> dict[str, Any]:
    tp, account = await _terms_account(request)
    async with tenant_tx(request, tp) as session:
        await _accept_portal_terms(
            session, tp.tenant_id, account, body.accept_terms, body.terms_version, request
        )
    return {"terms_version": body.terms_version, "accepted": True}


async def _terms_account(request: Request) -> tuple[TenantPrincipal, PortalAccount]:
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
                PortalAccount.user_id == principal.user_id,
                PortalAccount.status.in_(LOGIN_STATUSES),
            )
        )
    if account is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="No active portal account.")
    return tp, account


async def _scopes(session: AsyncSession, account: PortalAccount) -> dict[str, set[uuid.UUID]]:
    out: dict[str, set[uuid.UUID]] = {}
    for g in await access.grants(session, account, local_today()):
        out.setdefault(g.scope_type, set()).add(g.scope_id)
    return out


@router.get("/me", summary="Eigene Rollen und Verträge")
async def me(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind
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
        # M21-05: contracts reached only through a power of attorney do not make the account an
        # owner; the representative gets the own role "representative" instead.
        represented_contract_ids = {
            g.scope_id
            for g in active
            if g.scope_type == "contract" and g.legal_basis == access.REPRESENTATION_BASIS
        }
        contracts = (
            (await session.scalars(select(Contract).where(Contract.id.in_(contract_ids)))).all()
            if contract_ids
            else []
        )
        permissions = await access.staff_permissions(session, account)
        relations = PortalRelations(
            active_rental_contracts=sum(
                1 for c in contracts if c.kind is not ContractKind.OWNERSHIP
            ),
            active_ownerships=sum(
                1
                for c in contracts
                if c.kind is ContractKind.OWNERSHIP and c.id not in represented_contract_ids
            )
            + (1 if any(g.legal_basis in ("hoa_member_right",) for g in active) else 0),
            board_seats=1 if any(g.role == "board" for g in active) else 0,
            service_provider_relations=1 if is_provider else 0,
        )
        from mhvp.portal import features as portal_features

        feature_row = await portal_features.get_or_default(session)
        representations = await portal_features.active_representations(session, account)
        return {
            # M21-08: tenant feature switches the portal UI follows (chat, AI, support view).
            "features": portal_features.feature_dict(feature_row),
            # M21-05: powers of attorney held by this account (role switch in the UI).
            "representations": representations,
            "contact_id": account.contact_id,
            # GA11-01: language stored at the account (null: no choice yet).
            "locale": account.locale,
            # S16-10 (3.4): named portal roles derived from the relations, not assigned.
            "portal_roles": [r.value for r in derive_portal_roles(relations)]
            + (["representative"] if representations else []),
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


# GA11-01, GB14-01: portal languages. The portal derives its list from messages/*.json; the API
# validates against the setting ``MHVP_PORTAL_LOCALES`` (default de,en), so a further language is
# a message file plus one setting value, no code change.
PORTAL_LOCALES = ("de", "en")


def portal_locales(settings: Settings) -> tuple[str, ...]:
    codes = tuple(c.strip() for c in settings.portal_locales.split(",") if c.strip())
    return codes or PORTAL_LOCALES


class PortalLocaleIn(_In):
    locale: str | None = Field(default=None, max_length=8)


@router.patch("/me/locale", status_code=204, summary="Sprachwahl am Portalkonto speichern")
async def set_locale(
    body: PortalLocaleIn, request: Request, ctx: Portal = Depends(portal_user)
) -> None:
    principal, account = ctx
    if body.locale is not None and body.locale not in portal_locales(_settings(request)):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Sprache nicht verfügbar.")
    async with tenant_tx(request, principal) as session:
        row = await session.get(PortalAccount, account.id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.locale = body.locale


@router.get(
    "/notifications",
    summary="Eigene Benachrichtigungen (Portal)",
    dependencies=[Depends(strict_query)],
)
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


@router.get("/documents", summary="Freigegebene Dokumente", dependencies=[Depends(strict_query)])
async def documents(
    request: Request,
    ctx: Portal = Depends(portal_user),
    q: str | None = Query(default=None, max_length=100, description="Suche in Titel und Dateiname"),
    sort: str = Query(
        default="created_desc", pattern="^(created|title|filename)_(asc|desc)$|^created_desc$"
    ),
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        docs = await access.visible_documents(session, account, local_today(), q=q, sort=sort)
        ids = {d.id for d in docs}
        notes = await access.redaction_notes(session, ids)
        states = await read_receipts.states_for_account(session, account, ids)
        contexts = await _document_contexts(session, docs)
        return [
            {
                "id": d.id,
                "title": d.title,
                "filename": d.filename,
                "created_at": d.created_at,
                # E06, D31: a released version of a receipt carries the redaction note.
                "redaction_note": notes.get(d.id),
                # M21-02, SA-06: status neu/gelesen for this user, from the own read receipts
                # (an indication, see read_receipts.LEGAL_NOTE).
                "is_new": d.id not in states,
                "first_opened_at": states.get(d.id, {}).get("first"),
                "last_opened_at": states.get(d.id, {}).get("last"),
                "context": contexts.get(d.id),
            }
            for d in docs
        ]


def _filter_sort_documents(docs: list[Any], q: str | None, sort: str) -> list[Any]:
    """M25-06 (PÜ12): search and sort only within the documents the account may see."""
    needle = (q or "").strip().casefold()
    if needle:
        docs = [
            d
            for d in docs
            if needle in (d.title or "").casefold() or needle in d.filename.casefold()
        ]
    key, _, direction = sort.rpartition("_")
    field = {"created": "created_at", "title": "title", "filename": "filename"}[key]

    def sort_key(d: Any) -> Any:
        value = getattr(d, field)
        return value.casefold() if isinstance(value, str) else value

    return sorted(docs, key=sort_key, reverse=direction == "desc")


class PortalDocumentBundleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


@router.post("/documents/bundle", summary="Sammel-Download als ZIP mit Index (M25-06)")
async def documents_bundle(
    body: PortalDocumentBundleIn, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    """ZIP of the chosen documents with ``INDEX.csv``. The same visibility check as the single
    download applies; one unknown or foreign id answers 404 for the whole request. Each file
    is recorded as a download indication (D34)."""
    import csv
    import io
    import zipfile

    from mhvp.core.escaping import csv_safe_cell
    from mhvp.documents.blobs import BlobStore

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        visible = {d.id: d for d in await access.visible_documents(session, account, local_today())}
        ids = list(dict.fromkeys(body.document_ids))
        if any(i not in visible for i in ids):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await payment_files.ensure_not_payment_file(session, ids)  # GAJ-301
        store = BlobStore(request.app.state.settings)
        buffer = io.BytesIO()
        index = io.StringIO()
        writer = csv.writer(index, delimiter=";")
        writer.writerow(["Datei", "Titel", "Erstellt am", "Typ", "Größe in Byte"])
        used: set[str] = set()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for i, document_id in enumerate(ids, start=1):
                d = visible[document_id]
                data = store.get(d.storage_ref)
                safe = re.sub(r"[^\w.\- ]", "_", d.filename)
                name = f"{i:03d}_{safe}"
                while name in used:
                    name = f"x_{name}"
                used.add(name)
                archive.writestr(name, data)
                writer.writerow(  # formula injection (SECURITY-2026-10-01, Befund 4)
                    [
                        csv_safe_cell(name),
                        csv_safe_cell(d.title),
                        d.created_at.strftime("%d.%m.%Y"),
                        d.mime_type,
                        len(data),
                    ]
                )
                await read_receipts.record(session, account, d.id, "downloaded")
            archive.writestr("INDEX.csv", "\ufeff" + index.getvalue())
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.portal_bundle_download",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"count": len(ids)},
        )
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": content_disposition("attachment", "Belege.zip"),
                "X-Content-Type-Options": "nosniff",
            },
        )


async def _document_contexts(session: AsyncSession, docs: list[Any]) -> dict[uuid.UUID, str]:
    """Short context text per document (category name), SA-06."""
    from mhvp.documents.models import DocumentCategory

    category_ids = {d.category_id for d in docs if d.category_id is not None}
    if not category_ids:
        return {}
    rows = await session.execute(
        select(DocumentCategory.id, DocumentCategory.name).where(
            DocumentCategory.id.in_(category_ids)
        )
    )
    names: dict[uuid.UUID, str] = {r[0]: r[1] for r in rows.all()}
    return {d.id: names[d.category_id] for d in docs if d.category_id in names}


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
        if account.contact_id is not None:
            from mhvp.communication.receipts import mark_read_for_document

            # GA04-09: read indication on the sent mail that carried the document.
            await mark_read_for_document(session, account.contact_id, document.id)
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
        await payment_files.ensure_not_payment_file(session, [document.id])  # GAJ-301
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
    data = await read_limited(
        file,
        request.app.state.settings.document_max_bytes,
        detail="Die Datei ist zu groß.",
    )
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
            public_description=(
                f"Standort: {body.location.strip()}\n\n{body.description}"
                if body.location and body.location.strip()
                else body.description
            ),
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


async def portal_ticket_attachments(
    session: AsyncSession, ticket: Any, account: PortalAccount
) -> list[dict[str, Any]]:
    """Attachments of a ticket as the portal may show them (M19-03): ``external_attachments``
    none hides all, initiator_only shows the files this account uploaded itself, open all."""
    from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole

    policy = ticket.external_attachments
    if policy == "none":
        return []
    items = await ticket_attachments(session, ticket.id)
    if policy == "open" or not items:
        return items
    own = set(
        await session.scalars(
            select(Document.id)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == "ticket",
                DocumentLink.entity_id == ticket.id,
                DocumentLink.role == LinkRole.ATTACHMENT,
                Document.source == DocumentSource.PORTAL,
                Document.created_by == account.user_id,
            )
        )
    )
    return [a for a in items if a["id"] in own]


async def ticket_attachments(session: AsyncSession, ticket_id: uuid.UUID) -> list[dict[str, Any]]:
    """Documents linked to a ticket as attachments (A55). Shared with the CRM ticket detail
    (mhvp.tickets.routers.get_ticket)."""
    return await entity_attachments(session, "ticket", ticket_id)


@router.get(
    "/tickets", summary="Eigene Meldungen mit Verlauf", dependencies=[Depends(strict_query)]
)
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
            comment_query = (
                select(TicketComment)
                .where(
                    TicketComment.ticket_id == t.id,
                    TicketComment.internal.is_(False),
                    TicketComment.removed_at.is_(None),
                )
                .order_by(TicketComment.created_at)
            )
            # M19-03: none shows no comments, to_manager only the account's own ones.
            if t.external_comments == "none":
                comments: list[Any] = []
            else:
                if t.external_comments == "to_manager":
                    comment_query = comment_query.where(
                        TicketComment.author_contact_id == account.contact_id
                    )
                comments = list((await session.scalars(comment_query)).all())
            out.append(
                {
                    "id": t.id,
                    "number": t.number,
                    "title": t.title,
                    "status": t.status.value,
                    "comments": [c.body for c in comments],
                    "attachments": await portal_ticket_attachments(session, t, account),
                    # A58: open or accepted appointment proposals of the orders to this
                    # ticket; the resident accepts one via
                    # POST /portal/work-orders/{id}/appointment-proposals/{pid}/accept.
                    "appointment_proposals": await _ticket_proposals(session, t.id),
                    # GAF-35: completed orders of the ticket; the affected resident rates them
                    # via POST /portal/work-orders/{id}/rating (switch applies to display only).
                    "completed_work_order_ids": await _completed_order_ids(session, t.id),
                    # AM06 (GAJ-402): running status of the orders to this ticket (section 14
                    # "Status für Verwaltung und Bewohner sichtbar"); no provider, price or
                    # internal note is shown to the resident.
                    "work_orders": await _ticket_order_status(session, t.id),
                }
            )
        return out


async def _ticket_order_status(session: AsyncSession, ticket_id: uuid.UUID) -> list[dict[str, Any]]:
    from mhvp.tickets.models import OrderStatus, WorkOrder

    rows = (
        await session.scalars(
            select(WorkOrder)
            .where(WorkOrder.ticket_id == ticket_id, WorkOrder.status != OrderStatus.DRAFT)
            .order_by(WorkOrder.created_at)
        )
    ).all()
    return [
        {
            "id": o.id,
            "status": OrderStatus(o.status).value,
            "scheduled_at": o.scheduled_at,
        }
        for o in rows
    ]


async def _completed_order_ids(session: AsyncSession, ticket_id: uuid.UUID) -> list[uuid.UUID]:
    from mhvp.tickets.models import WorkOrder
    from mhvp.tickets.work_order_rating import RATABLE

    return list(
        (
            await session.scalars(
                select(WorkOrder.id)
                .where(WorkOrder.ticket_id == ticket_id, WorkOrder.status.in_(RATABLE))
                .order_by(WorkOrder.created_at)
            )
        ).all()
    )


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
        if ticket.external_comments == "none":
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Für diese Meldung sind keine Kommentare freigegeben."
            )
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
        from mhvp.documents.models import DocumentLink, LinkRole

        photos = await _own_uploads(session, account, body.document_ids)
        from mhvp.portal import features as portal_features

        photo_mode = (await portal_features.get_or_default(session)).meter_photo_mode or "hint"
        if photo_mode == "required" and not photos:
            raise ProblemError(ErrorCodes.PORTAL_METER_PHOTO_REQUIRED)
        payload = body.model_dump(mode="json")
        payload["document_ids"] = [str(d.id) for d in photos]
        photo_missing = photo_mode != "off" and not photos
        payload["photo_missing"] = photo_missing
        out = await _propose(session, principal, account, "meter_reading", payload)
        for doc in photos:
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=doc.id,
                    entity_type="portal_change_request",
                    entity_id=out["id"],
                    role=LinkRole.ATTACHMENT,
                )
            )
        await session.flush()
        out["attachments"] = [_attachment_out(d) for d in photos]
        out["photo_missing"] = photo_missing
        out["note"] = METER_PHOTO_MISSING_NOTE if photo_missing else None
        return out


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
    previous = order.status
    order.status = target
    await _announce_provider_step(session, order, previous, target, principal, note)


async def _announce_provider_step(
    session: AsyncSession,
    order: Any,
    previous: Any,
    target: Any,
    principal: TenantPrincipal,
    note: str,
) -> None:
    """M22-04: a status change made by the provider in the portal is announced like the CRM
    path: domain event ``work_order.<status>`` (source portal) and, for an order with a
    ticket, a ticket history entry that the management and the resident see."""
    await emit(
        session,
        tenant_id=order.tenant_id,
        type=f"work_order.{target.value}",
        entity_type="work_order",
        entity_id=order.id,
        actor_user_id=principal.user_id,
        payload={"source": "portal", "from": previous.value, "note": note},
    )
    await emit_completed_if_done(
        session,
        tenant_id=order.tenant_id,
        order_id=order.id,
        new_status=target,
        actor_user_id=principal.user_id,
        payload={"source": "portal", "from": previous.value},
    )
    _ticket_history(session, order, previous.value, target.value, principal, note)


def _ticket_history(
    session: AsyncSession, order: Any, from_: str, to: str, principal: TenantPrincipal, note: str
) -> None:
    from mhvp.tickets.models import TicketEvent

    if order.ticket_id is None:
        return
    session.add(
        TicketEvent(
            tenant_id=order.tenant_id,
            ticket_id=order.ticket_id,
            kind="work_order_status",
            user_id=principal.user_id,
            data={
                "work_order_id": str(order.id),
                "from": from_,
                "to": to,
                "source": "portal",
                "note": note,
            },
        )
    )


PROVIDER_ACCEPT_NOTE = "Portal: Auftrag angenommen"


async def _invoice_submissions(session: AsyncSession, order: Any) -> list[dict[str, Any]]:
    """M22-05: submissions for this order with their processing state (proposed, accepted,
    rejected) and the decision note of the management."""
    rows = (
        await session.scalars(
            select(ChangeRequest)
            .where(ChangeRequest.kind == "invoice_submission")
            .order_by(ChangeRequest.created_at.desc())
        )
    ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except ValueError:  # pragma: no cover - payload is written by submit_invoice
            continue
        if payload.get("work_order_id") != str(order.id):
            continue
        out.append(
            {
                "id": row.id,
                "number": payload.get("number"),
                "invoice_date": payload.get("invoice_date"),
                "gross": payload.get("gross"),
                "status": row.status,
                "decision_note": row.decision_note,
                "submitted_at": row.created_at,
            }
        )
    return out


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
    from mhvp.tickets.models import WorkOrderEvent

    accepted_at = await session.scalar(
        select(WorkOrderEvent.created_at)
        .where(
            WorkOrderEvent.work_order_id == o.id,
            WorkOrderEvent.note == PROVIDER_ACCEPT_NOTE,
        )
        .order_by(WorkOrderEvent.created_at)
        .limit(1)
    )
    return {
        "id": o.id,
        "description": o.description,
        "status": o.status.value,
        "quote_amount": o.quote_amount,
        # M22-06: id of the quote document (download through the portal document endpoints);
        # a quote without a document is flagged so the provider can add one.
        "quote_document_id": o.quote_document_id,
        "quote_document_missing": o.quote_amount is not None and o.quote_document_id is None,
        "accepted_by_provider_at": accepted_at,
        "invoice_submissions": await _invoice_submissions(session, o),
        "scheduled_at": o.scheduled_at,
        # A58: every proposal of this order with its status (proposed, accepted, declined,
        # superseded) and the execution photos linked as attachments.
        "appointment_proposals": [_proposal_out(p) for p in proposals],
        "photos": await entity_attachments(session, "work_order", o.id),
        # AC06: the resident's contact data only with a valid data_sharing consent.
        "resident_contact": await _resident_contact(session, o),
    }


async def _resident_contact(session: AsyncSession, o: Any) -> dict[str, Any]:
    from mhvp.tickets.order_sharing import order_contact_share

    share = await order_contact_share(session, o)
    return {"shared": share["shared"], "reason": share["reason"], "contact": share["contact"]}


@router.get(
    "/work-orders", summary="Eigene Aufträge (Dienstleister)", dependencies=[Depends(strict_query)]
)
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


@router.post("/work-orders/{order_id}/decline", summary="Auftrag ablehnen (mit Begründung)")
async def decline(
    order_id: uuid.UUID,
    request: Request,
    body: PortalDeclineIn | None = None,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.tickets.models import OrderStatus

    principal, account = ctx
    reason = (body.reason or "").strip() if body else ""
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        await _step(
            session,
            order,
            OrderStatus.REJECTED,
            principal,
            f"abgelehnt: {reason}" if reason else "abgelehnt",
        )
        return await _order(session, order)


@router.post("/work-orders/{order_id}/accept", summary="Auftrag annehmen (ohne Angebot)")
async def accept_order(
    order_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """M22-03: the provider confirms an order. Not an approval: the status stays unchanged
    (release, budget and board approval remain with the management); the confirmation is
    written to the order history and announced. Idempotent."""
    from mhvp.tickets.models import OrderStatus, WorkOrderEvent

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if order.status not in (OrderStatus.REQUESTED, OrderStatus.APPROVED):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Im Status {order.status.value} kann der Auftrag nicht angenommen werden.",
            )
        existing = await session.scalar(
            select(WorkOrderEvent.id).where(
                WorkOrderEvent.work_order_id == order.id,
                WorkOrderEvent.note == PROVIDER_ACCEPT_NOTE,
            )
        )
        if existing is None:
            session.add(
                WorkOrderEvent(
                    tenant_id=order.tenant_id,
                    work_order_id=order.id,
                    from_status=order.status.value,
                    to_status=order.status.value,
                    user_id=principal.user_id,
                    note=PROVIDER_ACCEPT_NOTE,
                )
            )
            await emit(
                session,
                tenant_id=order.tenant_id,
                type="work_order.provider_accepted",
                entity_type="work_order",
                entity_id=order.id,
                actor_user_id=principal.user_id,
                payload={"source": "portal"},
            )
            _ticket_history(
                session,
                order,
                order.status.value,
                order.status.value,
                principal,
                "Auftrag angenommen",
            )
            await session.flush()
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
        await session.flush()
        from mhvp.workspace.jobs import sync_work_order_entry

        await sync_work_order_entry(session, order)
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
    dependencies=[Depends(strict_query)],
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
        await session.flush()
        from mhvp.workspace.jobs import sync_work_order_entry

        await sync_work_order_entry(session, order)
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
        from mhvp.accounting.models import Invoice

        # V11-05: the invoice document must be an own portal upload of this provider.
        await _own_uploads(session, account, [body.document_id])

        number = body.number.strip()
        extra = _invoice_breakdown(body)
        booked = await session.scalar(
            select(Invoice.id).where(
                Invoice.provider_contact_id == order.provider_contact_id,
                func.lower(Invoice.number) == number.lower(),
            )
        )
        pending = [
            sub
            for sub in await _invoice_submissions(session, order)
            if str(sub["number"] or "").strip().lower() == number.lower()
            and sub["status"] in ("proposed", "accepted")
        ]
        if booked is not None or pending:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Eine Rechnung mit dieser Rechnungsnummer liegt bereits vor.",
            )
        return await _propose(
            session,
            principal,
            account,
            "invoice_submission",
            {**body.model_dump(mode="json"), **extra, "work_order_id": str(order.id)},
        )
