"""Default document categories, the free letter template and the standard retention profiles
per tenant (M6, A-017, M6-04).

Categories are the document types of section 11.4; the Drive folder mapping to the binding object
file structure (11.2) is a labelled assumption and can be changed per tenant.

Retention profiles: operator decision of 26.09.2026 (docs/OPEN_QUESTIONS.md M6-04, rule
docs/rules/M6-04-aufbewahrungsprofile.md). They are seeded as drafts only ("Entwurf, Prüfung
Steuerberatung offen"); a draft never unlocks a deletion (6.9.5). The seed is idempotent per
document class and never touches a row that already exists, so operator edits and releases
stay as they are. No legal norm is cited as verified: the source status is "Offene
Entscheidung" (owner Steuerberatung, V17).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import (
    DocumentCategory,
    DocumentTemplate,
    RetentionProfile,
    RetentionStart,
)

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


REVIEW_NOTE = "Entwurf, Prüfung Steuerberatung offen"
_BASIS = "Betreiberentscheidung 26.09.2026 (M6-04), Prüfung Steuerberatung offen; Anhang C {refs}"

# (document_class, years, months, permanent, start rule, references in annex C to verify)
STANDARD_RETENTION_PROFILES: tuple[tuple[str, int, int, bool, RetentionStart, str], ...] = (
    ("accounting_records", 10, 0, False, RetentionStart.END_OF_YEAR_CREATED, "R17, R18, R21"),
    ("journals", 10, 0, False, RetentionStart.END_OF_YEAR_LAST_ENTRY, "R17, R18"),
    ("statements", 10, 0, False, RetentionStart.STATEMENT_ISSUED, "R17, R18"),
    ("business_letters", 6, 0, False, RetentionStart.END_OF_YEAR_CREATED, "R17, R18"),
    ("tickets", 6, 0, False, RetentionStart.END_OF_YEAR_LAST_ENTRY, "R17, R18"),
    ("mails", 6, 0, False, RetentionStart.END_OF_YEAR_CREATED, "R17, R18"),
    ("contracts", 10, 0, False, RetentionStart.CONTRACT_END, "R17, R18"),
    ("portal_data", 0, 6, False, RetentionStart.PURPOSE_END, "S06 (Datenschutz)"),
    ("applicant_data", 0, 6, False, RetentionStart.PURPOSE_END, "S06 (Datenschutz)"),
    ("hoa_minutes", 0, 0, True, RetentionStart.END_OF_YEAR_CREATED, "S05 (WEG-Dauerunterlagen)"),
    (
        "hoa_resolutions",
        0,
        0,
        True,
        RetentionStart.END_OF_YEAR_CREATED,
        "S05 (WEG-Dauerunterlagen)",
    ),
)


async def ensure_retention_defaults(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Adds the missing standard profiles as drafts; returns how many were added.

    Existing rows of a class (edited, released or created by the operator) are never changed.
    The unique constraint does not cover ``legal_entity_kind IS NULL``, so the check is done
    here by class name for the tenant wide row.
    """
    existing = set(
        (
            await session.scalars(
                select(RetentionProfile.document_class).where(
                    RetentionProfile.legal_entity_kind.is_(None)
                )
            )
        ).all()
    )
    added = 0
    for document_class, years, months, permanent, start_rule, refs in STANDARD_RETENTION_PROFILES:
        if document_class in existing:
            continue
        session.add(
            RetentionProfile(
                tenant_id=tenant_id,
                document_class=document_class,
                legal_entity_kind=None,
                legal_basis=_BASIS.format(refs=refs),
                retention_years=years,
                retention_months=months,
                permanent=permanent,
                start_rule=start_rule,
                review_note=REVIEW_NOTE,
                created_by=None,
            )
        )
        added += 1
    await session.flush()
    return added


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
    await ensure_retention_defaults(session, tenant_id)
    await session.flush()
