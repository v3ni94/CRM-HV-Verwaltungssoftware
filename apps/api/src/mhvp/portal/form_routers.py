"""Portal forms (A56, A73): management of form templates (/api/v1/portal-admin/forms, with the
list of submissions per template) and the portal side (/api/v1/portal/forms, submissions). A
submission creates a ticket of the template's category with the values as structured text and
uploaded files as attachments; the portal user sees the ticket under "Meldungen" like a damage
report (visible_for initiator)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import forms
from mhvp.portal.forms import PortalFormSubmission, PortalFormTemplate
from mhvp.portal.routers import Portal, _scopes, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
admin = APIRouter(prefix="/portal-admin", tags=["Portal Verwaltung"])
READ = require_permission("tickets:read")
MANAGE = require_permission("tenant_settings:update")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FormFieldIn(_In):
    key: str = Field(min_length=1, max_length=60)
    label: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern="^(text|number|date|select|file)$")
    required: bool = False
    options: list[str] | None = None


class FormTemplateIn(_In):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(min_length=1, max_length=100)
    audience: str = Field(default="all", pattern="^(tenant|owner|all)$")
    active: bool = True
    sort_order: int = Field(default=0, ge=0, le=10000)
    fields: list[FormFieldIn] = Field(default_factory=list, max_length=forms.MAX_FIELDS)


class FormTemplatePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    audience: str | None = Field(default=None, pattern="^(tenant|owner|all)$")
    active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    fields: list[FormFieldIn] | None = Field(default=None, max_length=forms.MAX_FIELDS)


class FormSubmissionIn(_In):
    values: dict[str, Any] = Field(default_factory=dict)
    unit_id: uuid.UUID | None = None


def _out(t: PortalFormTemplate, *, admin_view: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "audience": t.audience,
        "fields": t.fields,
    }
    if admin_view:
        row.update(
            {
                "category": t.category,
                "active": t.active,
                "sort_order": t.sort_order,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
        )
    return row


# Management -----------------------------------------------------------------------------


@admin.get("/forms", summary="Formularvorlagen des Portals")
async def list_templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(PortalFormTemplate).order_by(
                PortalFormTemplate.sort_order, PortalFormTemplate.name
            )
        )
        return [_out(t, admin_view=True) for t in rows.all()]


@admin.post("/forms", status_code=201, summary="Formularvorlage anlegen")
async def create_template(
    body: FormTemplateIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, Any]:
    fields = forms.normalise_fields([f.model_dump() for f in body.fields])
    async with tenant_tx(request, principal) as session:
        t = PortalFormTemplate(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            name=body.name.strip(),
            description=(body.description or "").strip() or None,
            category=body.category.strip(),
            audience=body.audience,
            active=body.active,
            sort_order=body.sort_order,
            fields=fields,
        )
        session.add(t)
        await session.flush()
        await session.refresh(t)
        return _out(t, admin_view=True)


@admin.patch("/forms/{template_id}", summary="Formularvorlage ändern")
async def update_template(
    template_id: uuid.UUID,
    body: FormTemplatePatch,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        t = await session.get(PortalFormTemplate, template_id)
        if t is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if "fields" in data and data["fields"] is not None:
            t.fields = forms.normalise_fields(data.pop("fields"))
        for key, value in data.items():
            if key == "fields":
                continue
            if isinstance(value, str):
                value = value.strip() or None
                if value is None and key != "description":
                    raise ProblemError(ErrorCodes.VALIDATION, detail=f"{key} darf nicht leer sein.")
            setattr(t, key, value)
        t.updated_by = principal.user_id
        await session.flush()
        await session.refresh(t)
        return _out(t, admin_view=True)


@admin.delete("/forms/{template_id}", status_code=204, summary="Formularvorlage löschen")
async def delete_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> None:
    async with tenant_tx(request, principal) as session:
        t = await session.get(PortalFormTemplate, template_id)
        if t is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        used = await session.scalar(
            select(PortalFormSubmission.id)
            .where(PortalFormSubmission.template_id == template_id)
            .limit(1)
        )
        if used is not None:
            # Submissions reference the template; keep the history, deactivate instead.
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Zu dieser Vorlage liegen Einreichungen vor. Bitte deaktivieren.",
            )
        await session.delete(t)


@admin.get("/forms/{template_id}/submissions", summary="Einreichungen einer Formularvorlage")
async def list_submissions(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """A73: submissions per template for the CRM (newest first) with the portal account, the
    contact name and the ticket created from it. The values themselves are on the ticket
    (public description); only the identification is listed here (data minimisation)."""
    from mhvp.contacts.models import Contact
    from mhvp.portal.models import PortalAccount
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        t = await session.get(PortalFormTemplate, template_id)
        if t is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = (
            await session.execute(
                select(PortalFormSubmission, PortalAccount, Contact, Ticket)
                .join(PortalAccount, PortalAccount.id == PortalFormSubmission.account_id)
                .join(Contact, Contact.id == PortalAccount.contact_id)
                .join(Ticket, Ticket.id == PortalFormSubmission.ticket_id)
                .where(PortalFormSubmission.template_id == t.id)
                .order_by(PortalFormSubmission.created_at.desc(), PortalFormSubmission.id.desc())
                .limit(500)
            )
        ).all()
        return [
            {
                "id": s.id,
                "template_id": s.template_id,
                "account_id": account.id,
                "account_status": account.status,
                "contact_id": contact.id,
                "contact_name": contact.display_name,
                "created_at": s.created_at,
                "unit_id": ticket.unit_id,
                "ticket_id": ticket.id,
                "ticket_number": ticket.number,
                "ticket_status": ticket.status.value,
            }
            for s, account, contact, ticket in rows
        ]


# Portal ---------------------------------------------------------------------------------


async def _roles(session: Any, account: Any) -> set[str]:
    from mhvp.portal import access

    return {g.role for g in await access.grants(session, account, local_today())}


@router.get("/forms", summary="Formulare für die eigene Zielgruppe")
async def portal_forms(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        roles = await _roles(session, account)
        rows = await session.scalars(
            select(PortalFormTemplate)
            .where(PortalFormTemplate.active.is_(True))
            .order_by(PortalFormTemplate.sort_order, PortalFormTemplate.name)
        )
        return [
            _out(t, admin_view=False)
            for t in rows.all()
            if forms.audience_matches(t.audience, roles)
        ]


@router.post(
    "/forms/{template_id}/submissions", status_code=201, summary="Formular einreichen (Vorgang)"
)
async def submit_form(
    template_id: uuid.UUID,
    body: FormSubmissionIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.core.numbering import next_number
    from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole
    from mhvp.properties.models import Unit
    from mhvp.tickets.models import Priority, Ticket, TicketSource
    from mhvp.tickets.routers import SLA_HOURS

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        t = await session.get(PortalFormTemplate, template_id)
        if t is None or not t.active:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        roles = await _roles(session, account)
        if not forms.audience_matches(t.audience, roles):
            # Answered as not found: the portal never learns about forms of other audiences.
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        values = forms.validate_values(t.fields, body.values)
        # A55 rule: only documents this account uploaded itself may be attached.
        attachments: dict[str, str] = {}
        docs: list[Document] = []
        for f in t.fields:
            if f["type"] != "file":
                continue
            for document_id in values.get(f["key"], []):
                doc = await session.get(Document, uuid.UUID(document_id))
                if (
                    doc is None
                    or doc.created_by != account.user_id
                    or doc.source is not DocumentSource.PORTAL
                ):
                    raise ProblemError(
                        ErrorCodes.RESOURCE_NOT_FOUND, detail="Anhang nicht gefunden."
                    )
                attachments[document_id] = doc.filename or doc.title
                docs.append(doc)
        property_id = None
        if body.unit_id is not None:
            scopes = await _scopes(session, account)
            if body.unit_id not in scopes.get("unit", set()):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN, detail="Die Einheit gehört nicht zu Ihren Verträgen."
                )
            unit = await session.get(Unit, body.unit_id)
            property_id = unit.property_id if unit else None
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            title=t.name,
            category=t.category,
            public_description=forms.render_values(t, values, attachments),
            unit_id=body.unit_id,
            property_id=property_id,
            initiator_contact_id=account.contact_id,
            contact_id=account.contact_id,
            source=TicketSource.PORTAL,
            visible_for=["initiator"],
            sla_due_at=datetime.now(UTC) + timedelta(hours=SLA_HOURS[Priority.NORMAL]),
        )
        session.add(ticket)
        await session.flush()
        for doc in dict.fromkeys(docs):
            session.add(
                DocumentLink(
                    tenant_id=principal.tenant_id,
                    document_id=doc.id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                    role=LinkRole.ATTACHMENT,
                )
            )
        submission = PortalFormSubmission(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            template_id=t.id,
            account_id=account.id,
            ticket_id=ticket.id,
            values=values,
        )
        session.add(submission)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="portal_form.submitted",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=principal.user_id,
            payload={"template_id": str(t.id), "submission_id": str(submission.id)},
        )
        return {
            "id": submission.id,
            "ticket_id": ticket.id,
            "ticket_number": ticket.number,
            "status": ticket.status.value,
        }
