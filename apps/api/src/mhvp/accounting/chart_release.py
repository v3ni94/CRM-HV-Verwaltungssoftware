"""Release workflow of the chart of accounts template (M10-01/M10-02, V8, gate G1).

States per template version: ``draft`` (editable), ``in_review`` (handed to the tax advisor,
frozen), ``released`` (date, releaser, comment, optional tax advisor document; immutable). A
change after release creates a new version (``supersedes_id``) that starts as draft and needs
its own release. Gate G1 is only approved while a released version exists for the tenant
(``ensure_released_template``, called from the platform gate decision). The release itself is
an operator decision with the tax advisor (V8); this module records it, it does not decide it.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import ChartTemplate
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_RELEASED = "released"

STATUS_LABELS = {
    STATUS_DRAFT: "Entwurf",
    STATUS_IN_REVIEW: "zur Prüfung",
    STATUS_RELEASED: "freigegeben",
}


class ReleaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, max_length=2000)
    document_id: uuid.UUID | None = None


class AccountsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounts: list[dict[str, Any]]
    name: str | None = Field(default=None, max_length=200)


def _not_draft(template: ChartTemplate) -> ProblemError:
    return ProblemError(
        ErrorCodes.CHART_TEMPLATE_NOT_DRAFT,
        detail=(
            f"Kontenrahmen {template.code} Version {template.version} ist "
            f"{STATUS_LABELS.get(template.status, template.status)}. Änderungen erfordern eine "
            "neue Version mit erneuter Freigabe."
        ),
    )


async def _emit(
    session: AsyncSession,
    template: ChartTemplate,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    type: str,
    extra: dict[str, Any] | None = None,
) -> None:
    await emit(
        session,
        tenant_id=tenant_id,
        type=type,
        entity_type="chart_of_accounts_template",
        entity_id=template.id,
        actor_user_id=user_id,
        payload={"code": template.code, "version": template.version, **(extra or {})},
    )


async def submit_review(
    session: AsyncSession,
    template: ChartTemplate,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> ChartTemplate:
    if template.status != STATUS_DRAFT:
        raise _not_draft(template)
    template.status = STATUS_IN_REVIEW
    template.review_requested_at = datetime.now(UTC)
    template.review_requested_by = user_id
    await _emit(
        session, template, tenant_id=tenant_id, user_id=user_id, type="chart_template.in_review"
    )
    await session.flush()
    return template


async def back_to_draft(
    session: AsyncSession,
    template: ChartTemplate,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> ChartTemplate:
    if template.status != STATUS_IN_REVIEW:
        raise ProblemError(
            ErrorCodes.CHART_TEMPLATE_NOT_DRAFT,
            detail="Nur ein Kontenrahmen zur Prüfung kann in den Entwurf zurückgehen.",
        )
    template.status = STATUS_DRAFT
    await _emit(
        session, template, tenant_id=tenant_id, user_id=user_id, type="chart_template.draft"
    )
    await session.flush()
    return template


async def release(
    session: AsyncSession,
    template: ChartTemplate,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    comment: str | None,
    document_id: uuid.UUID | None,
) -> ChartTemplate:
    """Idempotent: a released version stays as it is (no second release, no overwrite)."""
    if template.status == STATUS_RELEASED or template.released:
        return template
    if document_id is not None:
        from mhvp.documents.models import Document

        if await session.get(Document, document_id) is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument des Steuerberaters nicht gefunden."
            )
    template.status = STATUS_RELEASED
    template.released = True
    template.released_by = user_id
    template.released_at = datetime.now(UTC)
    template.release_comment = comment
    template.release_document_id = document_id
    await _emit(
        session,
        template,
        tenant_id=tenant_id,
        user_id=user_id,
        type="chart_template.released",
        extra={"document_id": str(document_id) if document_id else None},
    )
    await session.flush()
    return template


async def new_version(
    session: AsyncSession,
    template: ChartTemplate,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> ChartTemplate:
    """Copy the accounts into a new draft version of the same code (highest version + 1)."""
    highest = await session.scalar(
        select(func.max(ChartTemplate.version)).where(ChartTemplate.code == template.code)
    )
    created = ChartTemplate(
        tenant_id=tenant_id,
        code=template.code,
        name=template.name,
        version=int(highest or template.version) + 1,
        accounts=[dict(row) for row in template.accounts],
        status=STATUS_DRAFT,
        supersedes_id=template.id,
    )
    session.add(created)
    await session.flush()
    await _emit(
        session,
        created,
        tenant_id=tenant_id,
        user_id=user_id,
        type="chart_template.version_created",
        extra={"supersedes": str(template.id)},
    )
    return created


async def update_accounts(
    session: AsyncSession,
    template: ChartTemplate,
    body: AccountsIn,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> ChartTemplate:
    if template.status != STATUS_DRAFT:
        raise _not_draft(template)
    numbers = [str(row.get("number", "")) for row in body.accounts]
    if len(numbers) != len(set(numbers)) or any(not n for n in numbers):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Kontonummern müssen gefüllt und eindeutig sein."
        )
    template.accounts = [dict(row) for row in body.accounts]
    if body.name:
        template.name = body.name
    await _emit(
        session,
        template,
        tenant_id=tenant_id,
        user_id=user_id,
        type="chart_template.updated",
        extra={"accounts": len(template.accounts)},
    )
    await session.flush()
    return template


async def history(session: AsyncSession, code: str) -> list[ChartTemplate]:
    rows = await session.scalars(
        select(ChartTemplate).where(ChartTemplate.code == code).order_by(ChartTemplate.version)
    )
    return list(rows.all())


async def released_template(session: AsyncSession) -> ChartTemplate | None:
    """The released version of the tenant (session is tenant scoped by RLS)."""
    row = await session.scalar(
        select(ChartTemplate)
        .where(ChartTemplate.status == STATUS_RELEASED)
        .order_by(ChartTemplate.version.desc())
        .limit(1)
    )
    return row if isinstance(row, ChartTemplate) else None


async def ensure_released_template(session: AsyncSession) -> ChartTemplate:
    """Gate G1 precondition (V8, M10-01/M10-02): raises MHVP-GATE-0004 without a release."""
    template = await released_template(session)
    if template is None:
        raise ProblemError(
            ErrorCodes.GATE_CHART_NOT_RELEASED,
            detail=(
                "Freigabestufe G1 setzt einen freigegebenen Kontenrahmen voraus (Entscheidung V8, "
                "Betreiber mit Steuerberater). Kontenrahmen unter Einstellungen, Buchhaltung, "
                "Kontenrahmen freigeben und den Antrag danach erneut genehmigen."
            ),
        )
    return template


# Exports for the tax advisor ---------------------------------------------------------------

EXPORT_COLUMNS = [
    ("number", "Kontonummer"),
    ("name", "Bezeichnung"),
    ("category", "Kategorie"),
    ("type", "Typ"),
    ("statement_kind", "Abrechnungsart"),
    ("allocation_category", "Umlagefähigkeit"),
    ("vat_option", "Umsatzsteueroption"),
    ("review_status", "Prüfstatus"),
    ("review_note", "Vermerk"),
]


def export_csv(template: ChartTemplate) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([label for _, label in EXPORT_COLUMNS] + ["Gilt für"])
    for row in sorted(template.accounts, key=lambda r: str(r.get("number", ""))):
        writer.writerow(
            [str(row.get(key, "") or "") for key, _ in EXPORT_COLUMNS]
            + [", ".join(row.get("applies_to", []))]
        )
    return out.getvalue()


def export_pdf(template: ChartTemplate, *, tenant_name: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Kontenrahmen {template.code} Version {template.version}",
    )
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=8, leading=10)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=13, leading=16)
    status = STATUS_LABELS.get(template.status, template.status)
    released = f"{template.released_at:%d.%m.%Y}" if template.released_at else "keine Freigabe"
    story: list[Any] = [
        Paragraph(
            f"Kontenrahmen {template.name} ({template.code}), Version {template.version}", head
        ),
        Paragraph(
            f"Mandant: {tenant_name}. Status: {status}. Freigabe: {released}."
            + (f" Kommentar: {template.release_comment}" if template.release_comment else ""),
            body,
        ),
        Paragraph(
            "Entwurf zur Prüfung durch die Steuerberatung (V8). Die Nummern folgen der "
            "Produktkonvention aus Kapitel 7.2, keine Rechtsnorm.",
            body,
        ),
        Spacer(1, 4 * mm),
    ]
    header = [Paragraph(label, body) for _, label in EXPORT_COLUMNS[:7]]
    rows = [header]
    for row in sorted(template.accounts, key=lambda r: str(r.get("number", ""))):
        rows.append([Paragraph(str(row.get(key, "") or ""), body) for key, _ in EXPORT_COLUMNS[:7]])
    widths = [20 * mm, 60 * mm, 20 * mm, 18 * mm, 22 * mm, 22 * mm, 18 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, (0, 0, 0)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()
