"""Daily jobs of section 15.1: ``tasks.digest`` (A40) and ``compliance.deadlines`` (A41).

Both jobs read data, write only their own tables (``digest_run``, ``compliance_deadline``)
and in-app notifications (``notify`` pattern), and never touch money or legally relevant
records. Dates are orientation only: the lead time comes from the tenant settings with a
documented default; the legal deadline calculation (time zone, receipt, end of period) is an
open operator decision (M1-09) and is neither computed nor claimed here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.config import Settings
from mhvp.core.ids import uuid7
from mhvp.workspace.models import ComplianceDeadline, DigestRun, WorkspaceJobSettings
from mhvp.workspace.services import local_date, notify

DEFAULT_LEAD_DAYS = 30
DEADLINE_KINDS: tuple[str, ...] = (
    "contract_end",
    "contract_termination",
    "meter_calibration",
    "bank_consent",
    "document_retention_end",
    "service_contract_notice",
    "meeting_resolution_deadline",
)
# Fixed lead time per kind; overrides the tenant setting (M9-06: 14 days for the notice date
# of service provider contracts).
DEADLINE_LEAD_DAYS: dict[str, int] = {
    "service_contract_notice": 14,
    "meeting_resolution_deadline": 7,
}
# Read permission needed to see a kind (endpoint) and update permission of the recipients of
# the "lead time reached" notification (job). Bank consents are additionally covered by the
# ten day reminder of A29 (``mhvp.banking.tasks``); this list is the long range view.
DEADLINE_PERMISSIONS: dict[str, tuple[str, str]] = {
    "contract_end": ("contracts:read", "contracts:update"),
    "contract_termination": ("contracts:read", "contracts:update"),
    "meter_calibration": ("properties:read", "properties:update"),
    "bank_consent": ("accounting:read", "accounting:update"),
    "document_retention_end": ("documents:read", "documents:update"),
    "service_contract_notice": ("contracts:read", "contracts:update"),
    # Same permissions as the owners' meeting endpoints of the HOA module (M9-07).
    "meeting_resolution_deadline": ("accounting:read", "accounting:update"),
}
DEADLINE_NOTIFICATION_KIND = "compliance_deadline"
DIGEST_NOTIFICATION_KIND = "daily_digest"
DIGEST_LIST_LIMIT = 10
OPEN_TICKET_STATUSES = ("new", "in_progress", "waiting")


# Settings -----------------------------------------------------------------------------


async def job_settings(session: AsyncSession, tenant_id: uuid.UUID) -> WorkspaceJobSettings:
    """Row of the tenant; a missing row is returned as transient defaults (not inserted)."""
    row = await session.scalar(
        select(WorkspaceJobSettings).where(WorkspaceJobSettings.tenant_id == tenant_id)
    )
    if row is None:
        row = WorkspaceJobSettings(
            tenant_id=tenant_id, digest_mail_enabled=False, deadline_lead_days=DEFAULT_LEAD_DAYS
        )
    return row


async def save_job_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    digest_mail_enabled: bool | None,
    deadline_lead_days: int | None,
    actor_user_id: uuid.UUID | None,
) -> WorkspaceJobSettings:
    row = await session.scalar(
        select(WorkspaceJobSettings).where(WorkspaceJobSettings.tenant_id == tenant_id)
    )
    if row is None:
        row = WorkspaceJobSettings(tenant_id=tenant_id, created_by=actor_user_id)
        session.add(row)
    if digest_mail_enabled is not None:
        row.digest_mail_enabled = digest_mail_enabled
    if deadline_lead_days is not None:
        row.deadline_lead_days = deadline_lead_days
    row.updated_by = actor_user_id
    await session.flush()
    return row


# Deadlines (A41) -----------------------------------------------------------------------


async def deadline_candidates(
    session: AsyncSession, tenant_id: uuid.UUID, today: date
) -> list[dict[str, Any]]:
    """Every future dated obligation known to the data model, keyed by (kind, source, date).

    Resolution deadlines of virtual owners' meetings come from the entered field with its
    source (M9-07), never from a computation. Service provider contracts are covered by
    ``service_contract_notice`` (M9-06).
    """
    from mhvp.banking.models import BankConnection, ConnectionStatus, FinApiConnection
    from mhvp.contracts.models import Contract
    from mhvp.contracts.service_contracts import ServiceContract, terms_of
    from mhvp.documents.models import Document
    from mhvp.hoa.models import Meeting
    from mhvp.properties.models import Meter, Property

    out: list[dict[str, Any]] = []

    def add(
        kind: str,
        source_type: str,
        source_id: uuid.UUID,
        reference: str,
        due_on: date | None,
        property_id: uuid.UUID | None = None,
    ) -> None:
        if due_on is None or due_on < today:
            return
        out.append(
            {
                "kind": kind,
                "source_type": source_type,
                "source_id": source_id,
                "reference": reference[:300],
                "due_on": due_on,
                "property_id": property_id,
            }
        )

    contracts = (
        await session.scalars(
            select(Contract).where(
                or_(Contract.end_date >= today, Contract.termination_date >= today)
            )
        )
    ).all()
    for c in contracts:
        label = "Mietvertrag" if c.kind.value == "tenancy" else "Eigentumsverhältnis"
        add("contract_end", "contract", c.id, f"{label} {c.number}", c.end_date, c.property_id)
        add(
            "contract_termination",
            "contract",
            c.id,
            f"{label} {c.number}",
            c.termination_date,
            c.property_id,
        )

    meters = (
        await session.execute(
            select(Meter, Property.number, Property.name)
            .join(Property, Property.id == Meter.property_id)
            .where(Meter.calibration_due_date >= today)
        )
    ).all()
    for meter, number, name in meters:
        add(
            "meter_calibration",
            "meter",
            meter.id,
            f"Zähler {meter.number} ({number} {name})",
            meter.calibration_due_date,
            meter.property_id,
        )

    connections = (
        await session.scalars(
            select(BankConnection).where(BankConnection.status != ConnectionStatus.DISABLED)
        )
    ).all()
    for conn in connections:
        fa = await session.scalar(
            select(FinApiConnection).where(FinApiConnection.bank_connection_id == conn.id)
        )
        valid_until = (fa.consent_valid_until if fa is not None else None) or (
            conn.consent_valid_until
        )
        add(
            "bank_consent",
            "bank_connection",
            conn.id,
            f"Bankzustimmung {conn.bank_name}",
            valid_until,
        )

    documents = (
        await session.execute(
            select(Document.id, Document.title, Document.retention_until).where(
                Document.retention_until >= today
            )
        )
    ).all()
    for doc_id, title, until in documents:
        add("document_retention_end", "document", doc_id, f"Aufbewahrung {title}", until)

    service_contracts = (
        await session.scalars(select(ServiceContract).where(ServiceContract.cancelled_at.is_(None)))
    ).all()
    for sc in service_contracts:
        add(
            "service_contract_notice",
            "service_contract",
            sc.id,
            f"Kündigungsfrist Dienstleistervertrag {sc.title}",
            terms_of(sc, today).notice_deadline,
            sc.property_id,
        )

    meetings = (
        await session.scalars(
            select(Meeting).where(
                Meeting.mode == "virtual", Meeting.resolution_deadline_at >= today
            )
        )
    ).all()
    for m in meetings:
        add(
            MEETING_RESOLUTION_KIND,
            "owners_meeting",
            m.id,
            meeting_deadline_reference(m.scheduled_at.date(), m.resolution_deadline_source),
            m.resolution_deadline_at,
        )
    return out


MEETING_RESOLUTION_KIND = "meeting_resolution_deadline"
# Fixed lead time of the resolution deadline (M9-07, Produktschutz), independent of the
# tenant switch: the entered date is orientation only and must be verified.
MEETING_RESOLUTION_LEAD_DAYS = 7


def meeting_deadline_reference(held_on: date, source: str | None) -> str:
    """Reference text of the deadline list entry, marked as orientation (M1-09)."""
    return (
        f"Beschlussfrist virtuelle Versammlung vom {held_on:%d.%m.%Y} "
        f"(Orientierung, zu prüfen; Quelle: {source or 'fehlt'})"
    )


def lead_days_for(kind: str, tenant_lead_days: int) -> int:
    """Fixed lead time per kind (``DEADLINE_LEAD_DAYS``), otherwise the tenant setting."""
    return DEADLINE_LEAD_DAYS.get(kind, tenant_lead_days)


async def refresh_deadlines(
    session: AsyncSession, tenant_id: uuid.UUID, today: date, lead_days: int
) -> dict[str, int]:
    """Upsert the deadline list from the sources; rows whose date vanished or passed are
    marked done. Idempotent: a second run on the same data changes nothing."""
    candidates = await deadline_candidates(session, tenant_id, today)
    existing = {
        (row.kind, row.source_id, row.due_on): row
        for row in (
            await session.scalars(
                select(ComplianceDeadline).where(ComplianceDeadline.status == "open")
            )
        ).all()
    }
    counts = {"created": 0, "updated": 0, "closed": 0}
    seen: set[tuple[str, uuid.UUID, date]] = set()
    now = datetime.now(UTC)
    for cand in candidates:
        key = (cand["kind"], cand["source_id"], cand["due_on"])
        seen.add(key)
        row = existing.get(key)
        if row is None:
            # A row closed earlier for the same key (date re-entered) is reopened, not
            # duplicated: the unique constraint covers all statuses.
            row = await session.scalar(
                select(ComplianceDeadline).where(
                    ComplianceDeadline.kind == cand["kind"],
                    ComplianceDeadline.source_id == cand["source_id"],
                    ComplianceDeadline.due_on == cand["due_on"],
                )
            )
            if row is None:
                session.add(
                    ComplianceDeadline(
                        tenant_id=tenant_id,
                        lead_days=lead_days_for(cand["kind"], lead_days),
                        status="open",
                        **cand,
                    )
                )
                counts["created"] += 1
                continue
            row.status, row.done_at = "open", None
            counts["updated"] += 1
        changed = False
        for field in ("reference", "property_id", "source_type"):
            if getattr(row, field) != cand[field]:
                setattr(row, field, cand[field])
                changed = True
        wanted_lead = lead_days_for(cand["kind"], lead_days)
        if row.lead_days != wanted_lead:
            row.lead_days, changed = wanted_lead, True
        counts["updated"] += int(changed)
    for key, row in existing.items():
        if key not in seen:
            row.status, row.done_at = "done", now
            counts["closed"] += 1
    await session.flush()
    return counts


async def notify_deadlines(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> int:
    """One notification per deadline row when the lead time is reached (``notified_at``)."""
    from mhvp.banking.tasks import users_with_permission

    rows = (
        await session.scalars(
            select(ComplianceDeadline).where(
                ComplianceDeadline.status == "open", ComplianceDeadline.notified_at.is_(None)
            )
        )
    ).all()
    due = [r for r in rows if r.due_on - timedelta(days=r.lead_days) <= today]
    if not due:
        return 0
    recipients: dict[str, list[uuid.UUID]] = {}
    created = 0
    for row in due:
        permission = DEADLINE_PERMISSIONS.get(row.kind, ("", "tenant_settings:update"))[1]
        if permission not in recipients:
            recipients[permission] = await users_with_permission(session, tenant_id, permission)
        days = (row.due_on - today).days
        for user_id in recipients[permission]:
            note = await notify(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                kind=DEADLINE_NOTIFICATION_KIND,
                title=f"Frist in {days} Tagen: {row.reference} ({row.due_on:%d.%m.%Y})",
                body=(
                    "Termin aus den Stammdaten, zu prüfen. Die Vorfrist stammt aus den "
                    f"Einstellungen ({row.lead_days} Tage). Rechtliche Fristen werden nicht "
                    "berechnet (M1-09)."
                ),
                entity_type="compliance_deadline",
                entity_id=row.id,
            )
            created += int(note is not None)
        row.notified_at = datetime.now(UTC)
    await session.flush()
    return created


async def deadlines_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, today: date
) -> dict[str, int]:
    settings_row = await job_settings(session, tenant_id)
    counts = await refresh_deadlines(session, tenant_id, today, settings_row.deadline_lead_days)
    counts["notified"] = await notify_deadlines(session, tenant_id, today)
    return counts


# Digest (A40) --------------------------------------------------------------------------


async def build_digest(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str] | set[str],
    today: date,
) -> dict[str, Any]:
    """Daily overview of one user; every section follows the user's permissions or their
    personal involvement (assignee, submitter). Read only."""
    from mhvp.ai.models import AiProposal, Decision
    from mhvp.tickets.models import Ticket, TicketAssignee

    sections: dict[str, Any] = {}

    if "tickets:read" in permissions:
        assigned = select(TicketAssignee.ticket_id).where(TicketAssignee.user_id == user_id)
        tickets = (
            await session.scalars(
                select(Ticket)
                .where(
                    Ticket.status.in_(OPEN_TICKET_STATUSES),
                    Ticket.sla_due_at.is_not(None),
                    or_(Ticket.assignee_user_id == user_id, Ticket.id.in_(assigned)),
                )
                .order_by(Ticket.sla_due_at)
            )
        ).all()
        due_today: list[dict[str, Any]] = []
        overdue: list[dict[str, Any]] = []
        for t in tickets:
            if t.sla_due_at is None:
                continue
            day = local_date(t.sla_due_at)
            item = {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "due_at": t.sla_due_at,
                "priority": t.priority.value,
            }
            if day == today:
                due_today.append(item)
            elif day < today:
                overdue.append(item)
        sections["tickets_due_today"] = _section(due_today)
        sections["tickets_overdue"] = _section(overdue)

    approvals: list[dict[str, Any]] = []
    if "accounting:approve" in permissions:
        from mhvp.accounting.models import Invoice, ReviewStatus

        rows = (
            await session.execute(
                select(Invoice.id, Invoice.number, Invoice.gross)
                .where(
                    Invoice.review_status.in_(
                        (ReviewStatus.OPEN, ReviewStatus.PARTIALLY_REVIEWED, ReviewStatus.QUERY)
                    )
                )
                .order_by(Invoice.invoice_date)
            )
        ).all()
        approvals += [
            {"kind": "invoice", "id": i, "title": f"Rechnung {n}", "amount": str(g)}
            for i, n, g in rows
        ]
    if "banking:approve" in permissions:
        from mhvp.banking.models import OrderStatus, PaymentApproval, PaymentOrder

        mine = select(PaymentApproval.order_id).where(
            PaymentApproval.user_id == user_id, PaymentApproval.invalidated_at.is_(None)
        )
        rows2 = (
            await session.execute(
                select(PaymentOrder.id, PaymentOrder.counterpart_name, PaymentOrder.amount)
                .where(PaymentOrder.status == OrderStatus.DRAFT, PaymentOrder.id.not_in(mine))
                .order_by(PaymentOrder.execution_date)
            )
        ).all()
        approvals += [
            {"kind": "payment", "id": i, "title": f"Zahlung {name}", "amount": str(a)}
            for i, name, a in rows2
        ]
    if "communication:approve" in permissions or "communication:create" in permissions:
        from mhvp.communication.models import Message

        where = [
            Message.direction == "out",
            Message.submitted_at.is_not(None),
            Message.approved_at.is_(None),
            Message.sent_at.is_(None),
            Message.rejection_note.is_(None),
        ]
        if "communication:approve" not in permissions:
            where.append(Message.submitted_by == user_id)
        rows3 = (
            await session.execute(
                select(Message.id, Message.subject).where(*where).order_by(Message.submitted_at)
            )
        ).all()
        approvals += [
            {"kind": "mail", "id": i, "title": f"Mail-Freigabe {s or '(ohne Betreff)'}"}
            for i, s in rows3
        ]
    sections["approvals"] = _section(approvals)

    deadline_rows = (
        await session.scalars(
            select(ComplianceDeadline)
            .where(ComplianceDeadline.status == "open", ComplianceDeadline.due_on >= today)
            .order_by(ComplianceDeadline.due_on)
        )
    ).all()
    deadlines = [
        {
            "id": r.id,
            "kind": r.kind,
            "reference": r.reference,
            "due_on": r.due_on,
            "lead_days": r.lead_days,
            "today": r.due_on == today,
        }
        for r in deadline_rows
        if DEADLINE_PERMISSIONS[r.kind][0] in permissions
        and (r.due_on == today or r.due_on - timedelta(days=r.lead_days) == today)
    ]
    sections["deadlines"] = _section(deadlines)

    if "ai:read" in permissions:
        rows4 = (
            await session.execute(
                select(AiProposal.id, AiProposal.entity_type, AiProposal.created_at)
                .where(AiProposal.decision == Decision.PENDING)
                .order_by(AiProposal.created_at)
            )
        ).all()
        sections["ai_proposals"] = _section(
            [{"id": i, "title": f"KI-Vorschlag {e}", "created_at": c} for i, e, c in rows4]
        )
    total = sum(int(s["count"]) for s in sections.values())
    return {"date": today, "total": total, "sections": sections}


def _section(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"count": len(items), "items": items[:DIGEST_LIST_LIMIT]}


def digest_text(digest: dict[str, Any]) -> str:
    """Plain German summary for the notification body and the optional system mail."""
    labels = {
        "tickets_due_today": "Heute fällige Tickets",
        "tickets_overdue": "Überfällige Tickets",
        "approvals": "Offene Freigaben",
        "deadlines": "Fristen des Tages (zu prüfen)",
        "ai_proposals": "Offene KI-Vorschläge",
    }
    lines: list[str] = []
    for key, section in digest["sections"].items():
        if not section["count"]:
            continue
        lines.append(f"{labels.get(key, key)}: {section['count']}")
        for item in section["items"]:
            title = item.get("title") or item.get("reference") or ""
            suffix = ""
            if "due_on" in item:
                suffix = f" ({item['due_on']:%d.%m.%Y})"
            elif "number" in item:
                title = f"#{item['number']} {title}"
            lines.append(f"  {title}{suffix}")
    return "\n".join(lines)


async def digest_tenant(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    today: date,
) -> dict[str, int]:
    """Per tenant half of ``tasks.digest``: one notification per active member and day,
    nothing for empty overviews, optional system mail (tenant switch, default off)."""
    from mhvp.core.auth.permissions import effective_permissions
    from mhvp.platform.models import Membership, MembershipStatus, User

    settings_row = await job_settings(session, tenant_id)
    members = (
        await session.execute(
            select(Membership.id, Membership.user_id, User.email)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.status == MembershipStatus.ACTIVE)
        )
    ).all()
    done_users = set(
        (
            await session.scalars(select(DigestRun.user_id).where(DigestRun.digest_date == today))
        ).all()
    )
    counts = {"users": 0, "notified": 0, "empty": 0, "skipped": 0, "mails": 0}
    for membership_id, user_id, email in members:
        counts["users"] += 1
        if user_id in done_users:
            counts["skipped"] += 1
            continue
        permissions, _roles = await effective_permissions(session, tenant_id, membership_id)
        digest = await build_digest(session, tenant_id, user_id, permissions, today)
        run = DigestRun(
            id=uuid7(),
            tenant_id=tenant_id,
            user_id=user_id,
            digest_date=today,
            counts={k: v["count"] for k, v in digest["sections"].items()},
            mail_status="empty" if digest["total"] == 0 else "not_sent",
        )
        session.add(run)
        if digest["total"] == 0:
            counts["empty"] += 1
            continue
        body = digest_text(digest)
        await notify(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=DIGEST_NOTIFICATION_KIND,
            title=f"Tagesübersicht {today:%d.%m.%Y}: {digest['total']} offene Punkte",
            body=body,
            entity_type="digest_run",
            entity_id=run.id,
        )
        counts["notified"] += 1
        if settings_row.digest_mail_enabled:
            from mhvp.sla.channels import send_email

            error = await send_email(
                session,
                settings,
                tenant_id,
                email,
                f"Tagesübersicht {today:%d.%m.%Y}",
                body + "\n\nAutomatische Systemmail der Verwaltungsplattform.",
            )
            run.mail_status = "sent" if error is None else "failed"
            if error is not None:
                run.counts = {**run.counts, "mail_error": error[:200]}
            counts["mails"] += int(error is None)
    await session.flush()
    return counts
