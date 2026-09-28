"""Standard folder structure of the property file (11.2) as the CRM describes it (Package F).

The six top level folders are fixed by the master prompt (section 11.2, ``dms.DRIVE_FOLDERS``).
The description of each folder is the filing rule of the handbook page
``docs/handbuch/anleitung-objektordner.md``; the software does not check it. The subfolders
of ``04_Mieterakte`` and ``05_Eigentümerakte`` are defined by the objektakte takeover
(``objektakte_document_class.subfolder_name`` after an import, docs/plans/M35); the CRM only
shows what was imported and never invents names (docs/OPEN_QUESTIONS.md, Package F).
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.dms import DRIVE_FOLDERS
from mhvp.documents.models import DocumentCategory

# (folder, description of the filing rule from the handbook, whether the folder is kept per
# unit and person with subfolders)
FOLDERS: tuple[tuple[str, str, bool], ...] = (
    (
        "01_Legitimationsunterlagen",
        "Ausweiskopien, Vollmachten, Erbscheine, Handelsregisterauszüge, SEPA-Mandate",
        False,
    ),
    (
        "02_Stammakte",
        "Teilungserklärung, Gemeinschaftsordnung, Verwaltervertrag, Pläne, Versicherungen, "
        "Protokolle und Beschlüsse, Dienstleisterverträge, Energieausweis",
        False,
    ),
    ("03_Buchhaltung", "Rechnungen, Abrechnungen, Wirtschaftspläne, Kontoauszüge", False),
    (
        "04_Mieterakte",
        "Je Einheit und Mieter: Mietvertrag, Nachträge, Kündigung, Übergabeprotokolle, "
        "Mieterhöhung, Korrespondenz",
        True,
    ),
    (
        "05_Eigentümerakte",
        "Je Einheit und Eigentümer: Grundbuchauszug, Kaufvertragsauszug, Korrespondenz, "
        "SEV-Vereinbarung",
        True,
    ),
    (
        "06_Sonstiges",
        "Unklar, Manuelle Prüfung, Dubletten, Nicht objektbezogen (Unterteilung durch die "
        "Software festgelegt)",
        False,
    ),
)

if tuple(f[0] for f in FOLDERS) != DRIVE_FOLDERS:  # pragma: no cover - module invariant
    raise RuntimeError("FOLDERS must describe exactly dms.DRIVE_FOLDERS in order")


async def folder_structure(session: AsyncSession) -> list[dict[str, Any]]:
    """Folders with their description, the tenant's categories pointing there and, for the
    person files, the subfolder names known from the objektakte takeover."""
    from mhvp.objektakte.models import ObjektakteDocumentClass

    categories = (
        await session.scalars(
            select(DocumentCategory).order_by(DocumentCategory.sort_order, DocumentCategory.name)
        )
    ).all()
    by_folder: dict[str, list[dict[str, Any]]] = {}
    category_folder: dict[Any, str | None] = {}
    for c in categories:
        category_folder[c.id] = c.drive_folder
        if c.drive_folder:
            by_folder.setdefault(c.drive_folder, []).append(
                {"id": c.id, "code": c.code, "name": c.name}
            )
    classes = (
        await session.scalars(
            select(ObjektakteDocumentClass)
            .where(ObjektakteDocumentClass.subfolder_name.is_not(None))
            .order_by(ObjektakteDocumentClass.subfolder_name, ObjektakteDocumentClass.type_name)
        )
    ).all()
    subfolders: dict[str, dict[str, list[str]]] = {}
    for k in classes:
        folder = category_folder.get(k.category_id) if k.category_id else None
        if not folder or not k.subfolder_name:
            continue
        types = subfolders.setdefault(folder, {}).setdefault(k.subfolder_name, [])
        if k.type_name and k.type_name not in types:
            types.append(k.type_name)
    out: list[dict[str, Any]] = []
    for folder, description, per_person in FOLDERS:
        out.append(
            {
                "folder": folder,
                "description": description,
                "per_unit_and_person": per_person,
                "categories": by_folder.get(folder, []),
                "subfolders": [
                    {"name": name, "document_types": types}
                    for name, types in subfolders.get(folder, {}).items()
                ],
                "subfolders_source": "objektakte" if subfolders.get(folder) else None,
            }
        )
    return out
