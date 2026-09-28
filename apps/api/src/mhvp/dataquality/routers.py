"""Data quality (Datenqualität) endpoints: report of records violating the entry standards and
an advisory check of a draft (rules ES-01 to ES-10). Read only: nothing is changed
automatically; fixing happens on the linked record by staff."""

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, or_, select

from mhvp.contacts.models import Contact, ContactEmail
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.dataquality import rules
from mhvp.properties.models import Property, PropertyStatus
from mhvp.tickets.models import Ticket, TicketStatus
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Datenqualität"])

# The report is master data centred; sections for properties and deadlines additionally need
# their own read permission and are left out (``sections_omitted``) without it.
READ = require_permission("contacts:read")
_OPEN_TICKET = (TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING)
_MAIL_ROLES = ("eigentuemer", "mieter")


class DataQualityFinding(BaseModel):
    rule: str
    field: str | None
    severity: Literal["error", "warning", "hint"]
    message: str


class DataQualityReportItem(BaseModel):
    entity_type: Literal["property", "contact", "ticket"]
    entity_id: str
    label: str
    findings: list[DataQualityFinding]


class DataQualityReportSection(BaseModel):
    key: Literal["properties", "contacts", "contact_emails", "deadlines"]
    total: int
    items: list[DataQualityReportItem]


class DataQualityReportOut(BaseModel):
    generated_on: date
    sections: list[DataQualityReportSection]
    sections_omitted: list[str] = Field(default_factory=list)


class DataQualityCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: Literal["property", "contact", "deadline"]
    data: dict[str, Any] = Field(default_factory=dict)


class DataQualityCheckOut(BaseModel):
    findings: list[DataQualityFinding]


def _out(findings: list[rules.Finding]) -> list[DataQualityFinding]:
    return [
        DataQualityFinding(rule=f.rule, field=f.field, severity=f.severity, message=f.message)
        for f in findings
    ]


def _section(key: Any, items: list[DataQualityReportItem], limit: int) -> DataQualityReportSection:
    return DataQualityReportSection(key=key, total=len(items), items=items[:limit])


@router.get("/data-quality/report", summary="Datenqualität: Verstöße gegen Erfassungsstandards")
async def report(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> DataQualityReportOut:
    today = local_today()
    sections: list[DataQualityReportSection] = []
    omitted: list[str] = []
    async with tenant_tx(request, principal) as session:
        if principal.has("properties:read"):
            props = (
                await session.scalars(
                    select(Property)
                    .where(Property.status != PropertyStatus.TERMINATED)
                    .order_by(Property.number)
                )
            ).all()
            items = []
            for p in props:
                found = rules.check_property(
                    {
                        "name": p.name,
                        "street": p.street,
                        "house_number": p.house_number,
                        "postal_code": p.postal_code,
                        "city": p.city,
                        "country": p.country,
                    }
                )
                if found:
                    items.append(
                        DataQualityReportItem(
                            entity_type="property",
                            entity_id=str(p.id),
                            label=f"{p.number} {p.name}",
                            findings=_out(found),
                        )
                    )
            sections.append(_section("properties", items, limit))
        else:
            omitted += ["properties"]

        people = (
            await session.scalars(
                select(Contact)
                .where(Contact.deleted_at.is_(None))
                .order_by(Contact.display_name, Contact.id)
            )
        ).all()
        name_items = []
        for c in people:
            found = [
                f
                for f in rules.check_contact(
                    {
                        "kind": c.kind.value,
                        "first_name": c.first_name,
                        "last_name": c.last_name,
                        "company_name": c.company_name,
                    }
                )
                if f.severity != "hint"
            ]
            if found:
                name_items.append(
                    DataQualityReportItem(
                        entity_type="contact",
                        entity_id=str(c.id),
                        label=c.display_name or "(ohne Namen)",
                        findings=_out(found),
                    )
                )
        sections.append(_section("contacts", name_items, limit))

        has_email = exists().where(ContactEmail.contact_id == Contact.id)
        without_mail = (
            await session.scalars(
                select(Contact)
                .where(
                    Contact.deleted_at.is_(None),
                    Contact.blocked.is_(False),
                    or_(*(Contact.roles.any(role) for role in _MAIL_ROLES)),  # type: ignore[arg-type]
                    ~has_email,
                )
                .order_by(Contact.display_name, Contact.id)
            )
        ).all()
        mail_items = [
            DataQualityReportItem(
                entity_type="contact",
                entity_id=str(c.id),
                label=c.display_name or "(ohne Namen)",
                findings=[
                    DataQualityFinding(
                        rule="ES-11",
                        field="emails",
                        severity="warning",
                        message=(
                            "Eigentümer oder Mieter ohne E-Mail-Adresse; eingehende Mails "
                            "können nicht automatisch zugeordnet werden."
                        ),
                    )
                ],
            )
            for c in without_mail
        ]
        sections.append(_section("contact_emails", mail_items, limit))

        if principal.has("tickets:read"):
            tickets = (
                await session.scalars(
                    select(Ticket)
                    .where(
                        Ticket.status.in_(_OPEN_TICKET),
                        Ticket.due_on.is_not(None),
                        Ticket.assignee_user_id.is_(None),
                    )
                    .order_by(Ticket.due_on, Ticket.number)
                )
            ).all()
            deadline_items = [
                DataQualityReportItem(
                    entity_type="ticket",
                    entity_id=str(t.id),
                    label=f"#{t.number} {t.title}",
                    findings=_out(
                        rules.check_deadline({"due_on": t.due_on, "assignee_user_id": None}, today)
                    ),
                )
                for t in tickets
            ]
            sections.append(_section("deadlines", deadline_items, limit))
        else:
            omitted += ["deadlines"]
    return DataQualityReportOut(generated_on=today, sections=sections, sections_omitted=omitted)


_CHECK_PERMISSION = {
    "property": "properties:read",
    "contact": "contacts:read",
    "deadline": "tickets:read",
}


@router.post("/data-quality/check", summary="Entwurf gegen Erfassungsstandards prüfen")
async def check(
    body: DataQualityCheckIn,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> DataQualityCheckOut:
    """Advisory check without side effects; warnings never block saving. Only ES-01 is also
    enforced by the property endpoints."""
    if not principal.has(_CHECK_PERMISSION[body.entity]):
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            developer_message=f"Missing permission {_CHECK_PERMISSION[body.entity]}.",
        )
    if body.entity == "property":
        found = rules.check_property(body.data)
    elif body.entity == "contact":
        found = rules.check_contact(body.data)
    else:
        try:
            found = rules.check_deadline(body.data, local_today())
        except (TypeError, ValueError) as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ungültiges Fristdatum.") from exc
    return DataQualityCheckOut(findings=_out(found))
