"""M35 Stufe 3 part 4 (docs/plans/M35-objektakte-uebernahme.md section 4): completeness check
per property, and the "Nachforderungsschreiben" draft body. Reuses `Property.management_type`
directly (`mhvp.properties.models.ManagementType`, see the note on
`ObjektakteRequiredDocument`), no separate "weg"/"rental" vocabulary.

A required document class is satisfied if the property has at least one `Document` linked to
it (`DocumentLink(entity_type="property", entity_id=property.id)`) whose `category_id` matches
the required `document_category_id`. This does not check document status, dates or content,
only presence — a stricter definition (e.g. "not older than the current accounting year") is a
later, explicitly decided rule, not assumed here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import Document, DocumentCategory, DocumentLink
from mhvp.objektakte.models import ObjektakteRequiredDocument
from mhvp.properties.models import Property


@dataclass
class MissingClass:
    document_category_id: str
    code: str
    name: str


@dataclass
class CompletenessResult:
    property_id: str
    management_type: str
    missing: list[MissingClass] = field(default_factory=list)
    satisfied: list[MissingClass] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "property_id": self.property_id,
            "management_type": self.management_type,
            "missing": [vars(m) for m in self.missing],
            "satisfied": [vars(m) for m in self.satisfied],
        }


async def check_completeness(
    session: AsyncSession, tenant_id: uuid.UUID, property_row: Property
) -> CompletenessResult:
    required_stmt = (
        select(ObjektakteRequiredDocument, DocumentCategory)
        .join(
            DocumentCategory,
            DocumentCategory.id == ObjektakteRequiredDocument.document_category_id,
        )
        .where(
            ObjektakteRequiredDocument.tenant_id == tenant_id,
            ObjektakteRequiredDocument.management_type == property_row.management_type,
            ObjektakteRequiredDocument.mandatory.is_(True),
        )
    )
    required = (await session.execute(required_stmt)).all()
    result = CompletenessResult(
        property_id=str(property_row.id), management_type=property_row.management_type.value
    )
    if not required:
        return result
    present_stmt = (
        select(Document.category_id)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .where(
            DocumentLink.entity_type == "property",
            DocumentLink.entity_id == property_row.id,
            Document.category_id.isnot(None),
        )
        .distinct()
    )
    present_ids = {row[0] for row in (await session.execute(present_stmt)).all()}
    for _required_row, category in required:
        entry = MissingClass(
            document_category_id=str(category.id), code=category.code, name=category.name
        )
        if category.id in present_ids:
            result.satisfied.append(entry)
        else:
            result.missing.append(entry)
    return result


def nachforderungsschreiben_text(
    property_row: Property, missing: list[MissingClass], *, today: datetime | None = None
) -> str:
    """German draft body for a "Nachforderungsschreiben" (rule 0.1.2: development is released,
    money is not — this is a text draft only, never sent; the caller marks it as "Entwurf" and
    a person reviews and sends it, matching the letters mechanism convention elsewhere)."""
    day = (today or datetime.now(UTC)).strftime("%d.%m.%Y")
    lines = [
        "ENTWURF — vor Versand prüfen und freigeben.",
        "",
        f"Betreff: Fehlende Unterlagen zur Objektakte {property_row.number}",
        "",
        f"Datum: {day}",
        "",
        "Sehr geehrte Damen und Herren,",
        "",
        (
            f"für die Objektakte {property_row.number} ({property_row.name}) fehlen uns "
            "derzeit noch folgende Unterlagen:"
        ),
        "",
    ]
    lines.extend(f"- {m.name}" for m in missing)
    lines += [
        "",
        "Wir bitten Sie, uns die genannten Unterlagen zeitnah zukommen zu lassen.",
        "",
        "Mit freundlichen Grüßen",
    ]
    return "\n".join(lines)
