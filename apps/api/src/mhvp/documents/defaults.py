"""Default document categories and the free letter template per tenant (M6, A-017).

Categories are the document types of section 11.4; the Drive folder mapping to the binding object
file structure (11.2) is a labelled assumption and can be changed per tenant.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import DocumentCategory, DocumentTemplate

CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("invoice", "Rechnung", "03_Buchhaltung"),
    ("contract", "Vertrag", "02_Stammakte"),
    ("minutes", "Protokoll", "02_Stammakte"),
    ("letter", "Schreiben", "06_Sonstiges"),
    ("statement", "Abrechnung", "03_Buchhaltung"),
    ("insurance", "Versicherung", "02_Stammakte"),
    ("declaration_of_division", "Teilungserklärung", "02_Stammakte"),
    ("photo", "Foto", "06_Sonstiges"),
    ("identification", "Legitimationsunterlage", "01_Legitimationsunterlagen"),
    ("other", "Sonstiges", "06_Sonstiges"),
)

# Free letter: subject and text are entered per letter, nothing is prefilled.
FREE_LETTER = (
    "free_letter",
    "Freier Brief",
    "{{ felder.betreff }}",
    "{{ empfaenger.anrede }}\n\n{{ felder.text }}",
)


async def ensure_document_defaults(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    existing = set((await session.scalars(select(DocumentCategory.code))).all())
    for order, (code, name, folder) in enumerate(CATEGORIES):
        if code not in existing:
            session.add(
                DocumentCategory(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    paperless_document_type=name,
                    drive_folder=folder,
                    sort_order=order,
                )
            )
    code, name, subject, body = FREE_LETTER
    if (
        await session.scalar(select(DocumentTemplate.id).where(DocumentTemplate.code == code))
        is None
    ):
        session.add(
            DocumentTemplate(tenant_id=tenant_id, code=code, name=name, subject=subject, body=body)
        )
    await session.flush()
