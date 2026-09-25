"""Lernphase Immoware24 (M33): rein lesende Erkundung von Struktur und Feldnutzung des DAV-
Spiegels, Uebernahme des Moduls Learning aus dem Immoware Hub
(/home/user/IMMOWARE24/app/Modules/Learning). Die drei Scanner arbeiten ausschliesslich auf den
bereits gespiegelten Zeilen (``ImmowareDavDocument``/``ImmowareDavContact``/``ImmowareDavEvent``),
kein zusaetzlicher DAV-Zugriff, kein Schreibpfad. ``LearningDiffer`` vergleicht die Rohbefunde
eines Laufs mit dem letzten erfolgreichen Lauf gleicher Art, reine Funktion ohne Seiteneffekte.
"""

import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.immoware.models import (
    ImmowareDavContact,
    ImmowareDavDocument,
    ImmowareDavEvent,
    LearningKind,
)

_OBJECT_NUMBER_RE = re.compile(r"(?:^|/)(\d{2,4})(?:[\s/]|$)")
_MAX_DEPTH = 3


def _folder_key(href: str) -> str:
    return href if href.endswith("/") else href + "/"


def compute_webdav_facts(rows: Sequence[Any]) -> dict[str, Any]:
    """Reine Auswertung fuer die Art webdav auf bereits geladenen Zeilen (Duck-Typing: href,
    is_collection, depth, size, display_name), ohne Datenbankzugriff. Ordnerbaum bis Tiefe 3."""
    folders: dict[str, dict[str, Any]] = {}
    extension_totals: Counter[str] = Counter()

    def _folder(href: str, depth: int) -> dict[str, Any]:
        key = _folder_key(href)
        if key not in folders:
            folders[key] = {
                "path": key,
                "depth": depth,
                "file_count": 0,
                "total_bytes": 0,
                "extensions": Counter(),
                "has_object_number": bool(_OBJECT_NUMBER_RE.search(key)),
            }
        return folders[key]

    for row in rows:
        depth = min(row.depth, _MAX_DEPTH)
        if row.is_collection:
            _folder(row.href, depth)
            continue
        parent = row.href.rsplit("/", 1)[0] if "/" in row.href.strip("/") else ""
        parent_depth = max(depth - 1, 0)
        folder = _folder(parent, parent_depth)
        folder["file_count"] += 1
        folder["total_bytes"] += row.size or 0
        extension = (
            (row.display_name or row.href).rsplit(".", 1)[-1].lower()
            if "." in (row.display_name or row.href)
            else "(ohne)"
        )
        folder["extensions"][extension] += 1
        extension_totals[extension] += 1

    folder_list = []
    for folder in sorted(folders.values(), key=lambda f: f["path"]):
        folder_list.append(
            {
                "path": folder["path"],
                "depth": folder["depth"],
                "file_count": folder["file_count"],
                "total_bytes": folder["total_bytes"],
                "extensions": dict(folder["extensions"]),
                "has_object_number": folder["has_object_number"],
            }
        )

    folder_count = len(folder_list)
    with_object_number = sum(1 for f in folder_list if f["has_object_number"])

    return {
        "kind": "webdav",
        "folder_count": folder_count,
        "folders": folder_list,
        "extension_totals": dict(extension_totals),
        "object_number_share": (with_object_number / folder_count) if folder_count else 0.0,
        "max_depth": _MAX_DEPTH,
    }


async def scan_webdav(session: AsyncSession, tenant_id: Any) -> dict[str, Any]:
    """Laedt die Zeilen des Dokumentenspiegels und wertet sie mit ``compute_webdav_facts`` aus."""
    rows = (
        await session.scalars(
            select(ImmowareDavDocument).where(ImmowareDavDocument.deleted_at.is_(None))
        )
    ).all()
    return compute_webdav_facts(rows)


_VCARD_SCALAR_FIELDS = ("fn", "org")
_VCARD_ARRAY_FIELDS = ("emails", "phones", "addresses")


def _normalized_email(value: str) -> str:
    return value.strip().lower()


def compute_carddav_facts(rows: Sequence[Any]) -> dict[str, Any]:
    """Reine Auswertung fuer die Art carddav: Feldnutzung je Kontaktfeld (Anteil gefuellt fuer
    FN, ORG, E-Mail, Telefon, Adresse), Anteil Kontakte mit E-Mail/Telefon/Adresse,
    Duplikatkandidaten nach normalisierter E-Mail. Zeilen per Duck-Typing (id, fn, org, emails,
    phones, addresses)."""
    total = len(rows)
    usage: dict[str, int] = {}
    for field in _VCARD_SCALAR_FIELDS:
        usage[field] = sum(1 for r in rows if getattr(r, field))
    for field in _VCARD_ARRAY_FIELDS:
        usage[field] = sum(1 for r in rows if getattr(r, field))

    email_index: dict[str, list[str]] = {}
    for row in rows:
        for email in row.emails or []:
            key = _normalized_email(email)
            if not key:
                continue
            email_index.setdefault(key, []).append(str(row.id))

    duplicate_candidates = [
        {"email": email, "contact_ids": ids} for email, ids in email_index.items() if len(ids) > 1
    ]

    return {
        "kind": "carddav",
        "mirrored_contacts": total,
        "field_usage": usage,
        "share_with_email": (usage.get("emails", 0) / total) if total else 0.0,
        "share_with_phone": (usage.get("phones", 0) / total) if total else 0.0,
        "share_with_address": (usage.get("addresses", 0) / total) if total else 0.0,
        "duplicate_candidates": duplicate_candidates,
    }


async def scan_carddav(session: AsyncSession, tenant_id: Any) -> dict[str, Any]:
    """Laedt die Zeilen des Adressbuchspiegels und wertet sie mit ``compute_carddav_facts`` aus."""
    rows = (
        await session.scalars(
            select(ImmowareDavContact).where(ImmowareDavContact.deleted_at.is_(None))
        )
    ).all()
    return compute_carddav_facts(rows)


_ICAL_SCALAR_FIELDS = ("summary", "location", "description")


def compute_caldav_facts(rows: Sequence[Any]) -> dict[str, Any]:
    """Reine Auswertung fuer die Art caldav: Feldnutzung je Terminfeld, Verteilung je Monat der
    letzten 12 Monate, Anteil ganztaegig, haeufigste SUMMARY-Praefixe (erstes Wort). Zeilen per
    Duck-Typing (summary, location, description, dtstart, dtend)."""
    total = len(rows)
    usage: dict[str, int] = {
        field: sum(1 for r in rows if getattr(r, field)) for field in _ICAL_SCALAR_FIELDS
    }

    all_day = sum(
        1
        for r in rows
        if r.dtstart is not None
        and r.dtend is not None
        and r.dtstart.hour == 0
        and r.dtstart.minute == 0
        and (r.dtend - r.dtstart).total_seconds() % 86400 == 0
    )

    now = datetime.now(UTC)
    months: Counter[str] = Counter()
    for row in rows:
        if row.dtstart is None:
            continue
        delta_months = (now.year - row.dtstart.year) * 12 + (now.month - row.dtstart.month)
        if 0 <= delta_months < 12:
            months[row.dtstart.strftime("%Y-%m")] += 1

    prefixes: Counter[str] = Counter()
    for row in rows:
        if row.summary:
            first_word = row.summary.strip().split(" ", 1)[0]
            if first_word:
                prefixes[first_word] += 1

    return {
        "kind": "caldav",
        "mirrored_events": total,
        "field_usage": usage,
        "all_day_share": (all_day / total) if total else 0.0,
        "events_per_month": dict(sorted(months.items())),
        "top_summary_prefixes": [
            {"prefix": prefix, "count": count} for prefix, count in prefixes.most_common(10)
        ],
    }


async def scan_caldav(session: AsyncSession, tenant_id: Any) -> dict[str, Any]:
    """Laedt die Zeilen des Kalenderspiegels und wertet sie mit ``compute_caldav_facts`` aus."""
    rows = (
        await session.scalars(select(ImmowareDavEvent).where(ImmowareDavEvent.deleted_at.is_(None)))
    ).all()
    return compute_caldav_facts(rows)


async def scan(session: AsyncSession, tenant_id: Any, kind: LearningKind) -> dict[str, Any]:
    if kind is LearningKind.WEBDAV:
        return await scan_webdav(session, tenant_id)
    if kind is LearningKind.CARDDAV:
        return await scan_carddav(session, tenant_id)
    return await scan_caldav(session, tenant_id)


def diff_facts(
    kind: LearningKind, previous: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    """Vergleicht die Rohbefunde mit dem letzten erfolgreichen Lauf gleicher Art. Liefert
    ``changed`` und eine Liste lesbarer Saetze unter ``changes``."""
    if previous is None:
        return {
            "changed": True,
            "first_run": True,
            "changes": ["Erster Lauf dieser Art, kein Vorlauf zum Vergleich."],
        }

    if kind is LearningKind.WEBDAV:
        return _diff_webdav(previous, current)
    return _diff_field_usage(kind, previous, current)


def _diff_webdav(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_paths = {f["path"] for f in previous.get("folders", [])}
    current_paths = {f["path"] for f in current.get("folders", [])}
    new_folders = sorted(current_paths - previous_paths)
    removed_folders = sorted(previous_paths - current_paths)

    changes: list[str] = []
    if new_folders:
        changes.append(
            f"{len(new_folders)} neue Ordner seit dem letzten Lauf, z. B. {new_folders[0]}."
        )
    if removed_folders:
        changes.append(
            f"{len(removed_folders)} Ordner sind im Spiegel nicht mehr vorhanden, "
            f"z. B. {removed_folders[0]}."
        )
    previous_extensions = set(previous.get("extension_totals", {}).keys())
    current_extensions = set(current.get("extension_totals", {}).keys())
    new_extensions = sorted(current_extensions - previous_extensions)
    if new_extensions:
        changes.append(f"Neue Dateiendungen aufgetreten: {', '.join(new_extensions)}.")

    return {
        "changed": bool(new_folders or removed_folders or new_extensions),
        "new_folders": new_folders,
        "removed_folders": removed_folders,
        "new_extensions": new_extensions,
        "changes": changes,
    }


def _diff_field_usage(
    kind: LearningKind, previous: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    previous_usage = previous.get("field_usage", {})
    current_usage = current.get("field_usage", {})

    newly_used: list[str] = []
    no_longer_used: list[str] = []
    for field, count in current_usage.items():
        before = int(previous_usage.get(field, 0))
        if before == 0 and int(count) > 0:
            newly_used.append(field)
    for field, count in previous_usage.items():
        after = int(current_usage.get(field, 0))
        if int(count) > 0 and after == 0:
            no_longer_used.append(field)

    changes: list[str] = []
    if newly_used:
        changes.append(f"Neu genutzte Felder: {', '.join(newly_used)}.")
    if no_longer_used:
        changes.append(f"Nicht mehr genutzte Felder: {', '.join(no_longer_used)}.")

    count_field = "mirrored_contacts" if kind is LearningKind.CARDDAV else "mirrored_events"
    previous_count = int(previous.get(count_field, 0))
    current_count = int(current.get(count_field, 0))
    if previous_count != current_count:
        changes.append(
            f"Anzahl gespiegelter Datensaetze von {previous_count} auf {current_count} geaendert."
        )

    return {
        "changed": bool(newly_used or no_longer_used or previous_count != current_count),
        "newly_used_fields": newly_used,
        "no_longer_used_fields": no_longer_used,
        "count_before": previous_count,
        "count_after": current_count,
        "changes": changes,
    }
