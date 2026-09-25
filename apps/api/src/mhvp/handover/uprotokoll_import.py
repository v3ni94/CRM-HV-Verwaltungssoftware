"""Data takeover from U-Protokoll (M30 stage 4, operator request 25.09.2026).

The productive U-Protokoll application (PHP/MariaDB, github.com/v3ni94/UProtkoll) is replaced by
this module (docs/plans/M30-uebergabeprotokoll.md). A `mysqldump` export (utf8mb4, schema per
`database/migrations/001_create_schema.sql` of that repository) is parsed without executing any
SQL: only `INSERT INTO ... VALUES (...), (...);` statements are read, tuple by tuple, handling
quoting, escaping and `NULL` the way MariaDB writes them. Import is always preview first (counts,
unmatched objects, duplicates by protocol number), then an explicit apply; apply is idempotent by
source id (`import_source = "uprotokoll:<protocols.id>"` on every created row, migration 0054).

Binary files (photos, signatures, the stored PDF) are not part of the SQL dump; they are matched
afterwards from a ZIP of the U-Protokoll storage directory by their stored path or SHA-256
(`match_files`), using the file metadata staged from `protocol_files` during `apply`.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal
from mhvp.handover.models import (
    HandoverDefect,
    HandoverItem,
    HandoverKey,
    HandoverMeter,
    HandoverNote,
    HandoverParticipant,
    HandoverProtocol,
    HandoverRoom,
)

# Tables of database/migrations/001_create_schema.sql (v3ni94/UProtkoll) that this importer
# understands. Anything else in the dump is still parsed (generic, table agnostic) and counted
# in the preview, but not applied: users (reference only, rule of the operator request: no
# accounts are created from it), audit_log, settings, login_attempts, protocol_templates,
# branches are out of scope for the CRM takeover.
KNOWN_TABLES = (
    "properties",
    "units",
    "protocols",
    "protocol_participants",
    "protocol_bank_details",
    "protocol_meters",
    "protocol_rooms",
    "protocol_defects",
    "protocol_keys",
    "protocol_items",
    "protocol_notes",
    "protocol_files",
    "protocol_signatures",
    "protocol_versions",
    "protocol_emails",
    "users",
)

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`?(?P<table>\w+)`?\s*\((?P<columns>[^()]*)\)\s*VALUES\s*"
    r"(?P<values>.*?)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_KIND_MAP = {"rental": "rental", "sale": "sale", "general": "general"}
_STATUS_MAP = {
    "draft": "draft",
    "in_progress": "in_progress",
    "signature_pending": "signature_pending",
    "completed": "completed",
    "sent": "sent",
    "archived": "archived",
    "cancelled": "cancelled",
    "rework": "in_progress",  # no equivalent status in the CRM (M30-01); treated as in progress
}


def _strip_comments(sql: str) -> str:
    """mysqldump comments: `-- ...` line comments and `/* ... */` block comments outside of
    string literals. A dump never places these markers inside a data value, so a line based
    strip is sufficient and never touches an INSERT statement's own content."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    kept = []
    for line in sql.split("\n"):
        if line.strip().startswith("--"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _split_columns(columns: str) -> list[str]:
    return [c.strip().strip("`") for c in columns.split(",") if c.strip()]


def _tuples(values: str) -> list[str]:
    """Split "(...), (...)" into the inner text of each tuple, respecting quoted strings so a
    comma or a parenthesis inside a value never ends the tuple early."""
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    in_string: str | None = None
    i, n = 0, len(values)
    while i < n:
        ch = values[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                buf.append(ch)
                buf.append(values[i + 1])
                i += 2
                continue
            if ch == in_string:
                if i + 1 < n and values[i + 1] == in_string:  # doubled quote = literal quote
                    buf.append(ch)
                    buf.append(ch)
                    i += 2
                    continue
                in_string = None
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "(":
            depth += 1
            if depth == 1:
                buf = []
                i += 1
                continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                out.append("".join(buf))
                i += 1
                continue
        if depth > 0:
            buf.append(ch)
        i += 1
    return out


def _coerce(text: str, quoted: bool) -> Any:
    if quoted:
        return text
    stripped = text.strip()
    if stripped == "" or stripped.upper() == "NULL":
        return None
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _fields(tup: str) -> list[Any]:
    """One tuple's fields, unescaped and typed: a quoted field stays a string (even "123"), an
    unquoted field becomes int/float/None (NULL) the way MariaDB writes literals."""
    out: list[Any] = []
    buf: list[str] = []
    quoted = False
    in_string: str | None = None
    i, n = 0, len(tup)
    while i < n:
        ch = tup[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                nxt = tup[i + 1]
                buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0"}.get(nxt, nxt))
                i += 2
                continue
            if ch == in_string:
                if i + 1 < n and tup[i + 1] == in_string:
                    buf.append(ch)
                    i += 2
                    continue
                in_string = None
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            quoted = True
            i += 1
            continue
        if ch == ",":
            out.append(_coerce("".join(buf), quoted))
            buf, quoted = [], False
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append(_coerce("".join(buf), quoted))
    return out


def parse_dump(sql_text: str) -> dict[str, list[dict[str, Any]]]:
    """Every `INSERT INTO` statement of the dump, grouped by table. Rows whose value count does
    not match the column list are skipped (malformed statement, e.g. a truncated upload) rather
    than raising, so one bad statement never blocks the rest of the dump."""
    cleaned = _strip_comments(sql_text)
    tables: dict[str, list[dict[str, Any]]] = {}
    for m in _INSERT_RE.finditer(cleaned):
        table = m.group("table").lower()
        columns = _split_columns(m.group("columns"))
        for tup in _tuples(m.group("values")):
            values = _fields(tup)
            if len(values) != len(columns):
                continue
            tables.setdefault(table, []).append(dict(zip(columns, values, strict=False)))
    return tables


# --- typed conversions of MariaDB literals to the CRM's Python/SQLAlchemy types -----------------


def _s(row: dict[str, Any], key: str, limit: int | None = None) -> str | None:
    v = row.get(key)
    if v is None:
        return None
    text = str(v).strip()
    if text == "":
        return None
    return text[:limit] if limit else text


def _to_date(v: Any) -> date | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()  # noqa: DTZ007 -- MariaDB DATE has no tz
    except ValueError:
        return None


def _to_time(v: Any) -> time | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:8], "%H:%M:%S").time()  # noqa: DTZ007 -- MariaDB TIME has no tz
    except ValueError:
        return None


def _to_datetime(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007 -- MariaDB DATETIME has no tz
    except ValueError:
        return None


# Public alias: `mhvp.handover.imports` (the file-matching endpoint) needs the same conversion
# for `protocol_signatures.signed_at`, staged as a plain string in `ImportRun.summary`.
to_datetime = _to_datetime


def _to_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _to_bool(v: Any) -> bool:
    return bool(v) and str(v) not in ("0", "0.0")


async def _match_property(
    session: AsyncSession, tenant_id: uuid.UUID, src: dict[str, Any] | None
) -> uuid.UUID | None:
    """Exact address match against the CRM portfolio (street, house number, postal code, city).
    No fuzzy matching: a near miss becomes a manual, snapshot-only object (part A of the M30
    operator request) rather than a wrong link."""
    if src is None:
        return None
    from mhvp.properties.models import Property

    street, house_number = _s(src, "street"), _s(src, "house_number") or ""
    postal_code, city = _s(src, "postal_code"), _s(src, "city")
    if not (street and postal_code and city):
        return None
    matched: uuid.UUID | None = await session.scalar(
        select(Property.id).where(
            Property.tenant_id == tenant_id,
            func.lower(Property.street) == street.lower(),
            func.lower(func.coalesce(Property.house_number, "")) == house_number.lower(),
            Property.postal_code == postal_code,
            func.lower(Property.city) == city.lower(),
        )
    )
    return matched


@dataclass
class ImportPlan:
    counts: dict[str, int] = field(default_factory=dict)
    protocols: list[dict[str, Any]] = field(default_factory=list)
    unmatched_objects: int = 0
    duplicates: int = 0
    unknown_tables: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "protocols": self.protocols,
            "unmatched_objects": self.unmatched_objects,
            "duplicates": self.duplicates,
            "unknown_tables": self.unknown_tables,
        }


async def build_plan(
    session: AsyncSession, tenant_id: uuid.UUID, tables: dict[str, list[dict[str, Any]]]
) -> ImportPlan:
    protocols = tables.get("protocols", [])
    properties_by_id = {p.get("id"): p for p in tables.get("properties", [])}
    existing = frozenset(
        (
            await session.scalars(
                select(HandoverProtocol.import_source).where(
                    HandoverProtocol.tenant_id == tenant_id,
                    HandoverProtocol.import_source.is_not(None),
                )
            )
        ).all()
    )
    plan = ImportPlan(counts={t: len(rows) for t, rows in tables.items()})
    plan.unknown_tables = sorted(set(tables) - set(KNOWN_TABLES))
    for row in protocols:
        source_id = f"uprotokoll:{row.get('id')}"
        duplicate = source_id in existing
        if duplicate:
            plan.duplicates += 1
        prop = properties_by_id.get(row.get("property_id"))
        matched = await _match_property(session, tenant_id, prop) if prop else None
        if prop is not None and matched is None:
            plan.unmatched_objects += 1
        plan.protocols.append(
            {
                "source_id": row.get("id"),
                "number": row.get("protocol_number"),
                "version": row.get("version") or 1,
                "status": row.get("status"),
                "address": ", ".join(
                    x
                    for x in (
                        row.get("street"),
                        row.get("house_number"),
                        row.get("postal_code"),
                        row.get("city"),
                    )
                    if x
                ),
                "matched_property": matched is not None,
                "duplicate": duplicate,
            }
        )
    return plan


@dataclass
class ImportResult:
    created: dict[str, int] = field(default_factory=dict)
    skipped_duplicates: int = 0
    id_map: dict[str, dict[str, str]] = field(default_factory=dict)
    staged_files: list[dict[str, Any]] = field(default_factory=list)
    signatures: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped_duplicates": self.skipped_duplicates,
            "id_map": self.id_map,
            "staged_files": self.staged_files,
            "signatures": self.signatures,
        }


async def apply_import(
    session: AsyncSession,
    principal: TenantPrincipal,
    tables: dict[str, list[dict[str, Any]]],
) -> ImportResult:
    """Creates protocols and their sub records. Idempotent: a protocol whose
    `uprotokoll:<id>` source is already present is skipped entirely (its sub records were
    created together with it in an earlier run). Signatures and photos are not created here;
    `protocol_files` rows are staged in the result for the second endpoint (ZIP of the storage
    directory), since the SQL dump never carries binary data."""
    tenant_id = principal.tenant_id
    result = ImportResult()
    protocol_map: dict[Any, uuid.UUID] = {}
    room_map: dict[Any, uuid.UUID] = {}
    properties_by_id = {p.get("id"): p for p in tables.get("properties", [])}
    existing = frozenset(
        (
            await session.scalars(
                select(HandoverProtocol.import_source).where(
                    HandoverProtocol.tenant_id == tenant_id,
                    HandoverProtocol.import_source.is_not(None),
                )
            )
        ).all()
    )

    def _created(kind: str) -> None:
        result.created[kind] = result.created.get(kind, 0) + 1

    for row in tables.get("protocols", []):
        source_id = f"uprotokoll:{row.get('id')}"
        if source_id in existing:
            result.skipped_duplicates += 1
            continue
        prop = properties_by_id.get(row.get("property_id"))
        matched_property_id = await _match_property(session, tenant_id, prop) if prop else None
        p = HandoverProtocol(
            tenant_id=tenant_id,
            created_by=principal.user_id,
            import_source=source_id,
            number=_s(row, "protocol_number") or f"UP-IMPORT-{row.get('id')}",
            version=int(row.get("version") or 1),
            kind=_KIND_MAP.get(_s(row, "protocol_type") or "rental", "rental"),
            status=_STATUS_MAP.get(_s(row, "status") or "draft", "draft"),
            current_step="summary",
            property_id=matched_property_id,
            street=_s(row, "street", 200),
            house_number=_s(row, "house_number", 20),
            postal_code=_s(row, "postal_code", 20),
            city=_s(row, "city", 100),
            object_label=_s(row, "object_label", 200),
            building=_s(row, "building", 100),
            floor=_s(row, "floor", 20),
            unit_number=_s(row, "unit_number", 50),
            unit_label=_s(row, "unit_label", 100),
            unit_position=_s(row, "unit_position", 100),
            external_object_number=_s(row, "internal_object_number", 100),
            handover_date=_to_date(row.get("handover_date")),
            handover_start=_to_time(row.get("handover_start")),
            handover_end=_to_time(row.get("handover_end")),
            hide_time_information=_to_bool(row.get("hide_time_information")),
            handover_location=_s(row, "handover_location", 200),
            ticket_number=_s(row, "ticket_number", 50),
            reference_number=_s(row, "reference_number", 100),
            management_number=_s(row, "management_number", 100),
            rental_contract_number=_s(row, "rental_contract_number", 100),
            internal_contact=_s(row, "internal_contact", 200),
            internal_note=_s(row, "internal_note"),
            general_note=_s(row, "general_note"),
            completed_at=_to_datetime(row.get("completed_at")),
            archived_at=_to_datetime(row.get("archived_at")),
        )
        session.add(p)
        await session.flush()
        protocol_map[row.get("id")] = p.id
        _created("protocols")

    result.id_map["protocols"] = {str(k): str(v) for k, v in protocol_map.items()}
    if not protocol_map:
        return result

    for row in tables.get("protocol_participants", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        session.add(
            HandoverParticipant(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                role=_s(row, "role", 20) or "other",
                salutation=_s(row, "salutation", 50),
                first_name=_s(row, "first_name", 100),
                last_name=_s(row, "last_name", 100),
                company=_s(row, "company", 200),
                street=_s(row, "street", 200),
                house_number=_s(row, "house_number", 20),
                postal_code=_s(row, "postal_code", 20),
                city=_s(row, "city", 100),
                email=_s(row, "email", 320),
                phone=_s(row, "phone", 50),
                comment=_s(row, "comment"),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("participants")

    for row in tables.get("protocol_meters", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        session.add(
            HandoverMeter(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                meter_type=_s(row, "meter_type", 63),
                custom_type=_s(row, "custom_type", 100),
                number=_s(row, "meter_number", 100),
                value=_to_decimal(row.get("meter_value")),
                unit=_s(row, "unit", 20),
                location=_s(row, "location", 200),
                read_on=_to_date(row.get("reading_date")),
                read_at=_to_time(row.get("reading_time")),
                comment=_s(row, "comment"),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("meters")

    for row in tables.get("protocol_rooms", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        room = HandoverRoom(
            tenant_id=tenant_id,
            created_by=principal.user_id,
            import_source=f"uprotokoll:{row.get('id')}",
            protocol_id=pid,
            room_type=_s(row, "room_type", 100),
            name=_s(row, "room_name", 200),
            condition=_s(row, "condition_status", 20),
            comment=_s(row, "comment"),
            sort_order=int(row.get("sort_order") or 0),
        )
        session.add(room)
        await session.flush()
        room_map[row.get("id")] = room.id
        _created("rooms")
    result.id_map["rooms"] = {str(k): str(v) for k, v in room_map.items()}

    for row in tables.get("protocol_defects", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        session.add(
            HandoverDefect(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                room_id=room_map.get(row.get("room_id")),
                category=_s(row, "category", 100),
                title=_s(row, "title", 200),
                description=_s(row, "description"),
                location=_s(row, "location", 200),
                priority=_s(row, "priority", 10),
                responsibility=_s(row, "responsibility", 100),
                defect_status=_s(row, "defect_status", 20),
                comment=_s(row, "comment"),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("defects")

    for row in tables.get("protocol_keys", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        session.add(
            HandoverKey(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                key_type=_s(row, "key_type", 100),
                custom_name=_s(row, "custom_name", 200),
                quantity=row.get("quantity"),
                key_number=_s(row, "key_number", 100),
                status=_s(row, "status", 20),
                comment=_s(row, "comment"),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("keys")

    for row in tables.get("protocol_items", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        session.add(
            HandoverItem(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                item_type=_s(row, "item_type", 100),
                name=_s(row, "name", 200),
                quantity=row.get("quantity"),
                condition=_s(row, "condition_status", 100),
                comment=_s(row, "comment"),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("items")

    for row in tables.get("protocol_notes", []):
        pid = protocol_map.get(row.get("protocol_id"))
        if pid is None:
            continue
        text = " ".join(x for x in (_s(row, "text"), _s(row, "comment")) if x) or None
        session.add(
            HandoverNote(
                tenant_id=tenant_id,
                created_by=principal.user_id,
                import_source=f"uprotokoll:{row.get('id')}",
                protocol_id=pid,
                category=_s(row, "category", 20),
                text=text,
                responsible_party=_s(row, "responsible_party", 200),
                due_date=_to_date(row.get("due_date")),
                status=_s(row, "status", 50),
                is_internal=_to_bool(row.get("is_internal")),
                sort_order=int(row.get("sort_order") or 0),
            )
        )
        _created("notes")

    result.staged_files = [
        {
            "source_id": row.get("id"),
            "protocol_source_id": row.get("protocol_id"),
            "room_source_id": row.get("room_id"),
            "defect_source_id": row.get("defect_id"),
            "meter_source_id": row.get("meter_id"),
            "item_source_id": row.get("item_id"),
            "file_category": _s(row, "file_category", 60),
            "attachment_type": _s(row, "attachment_type", 60),
            "original_filename": _s(row, "original_filename", 255),
            "storage_path": _s(row, "storage_path", 500),
            "mime_type": _s(row, "mime_type", 120),
            "sha256": _s(row, "sha256", 64),
            "description": _s(row, "description", 255),
            "is_internal": _to_bool(row.get("is_internal")),
        }
        for row in tables.get("protocol_files", [])
        if protocol_map.get(row.get("protocol_id")) is not None
    ]
    result.signatures = [
        {
            "signature_file_id": row.get("signature_file_id"),
            "signer_name": _s(row, "signer_name", 200),
            "signer_role": _s(row, "signer_role", 20),
            "signed_at": row.get("signed_at"),
            "signed_location": _s(row, "signed_location", 200),
            "comment": _s(row, "comment", 255),
        }
        for row in tables.get("protocol_signatures", [])
        if protocol_map.get(row.get("protocol_id")) is not None
    ]
    await session.flush()
    return result
