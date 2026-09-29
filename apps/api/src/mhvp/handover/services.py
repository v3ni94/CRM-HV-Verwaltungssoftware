"""Handover protocol services (M30): numbering, loading, hints, versions, completion.

Business rules are product protection (docs/rules/M30-01.md): no mandatory content field,
locked protocols are never edited in place, a new version copies every sub record and
references the same documents (no duplicate files), the original stays unchanged.
"""

import hashlib
import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole
from mhvp.handover.models import (
    LOCKED_STATUSES,
    HandoverChange,
    HandoverDefect,
    HandoverItem,
    HandoverKey,
    HandoverMeter,
    HandoverNote,
    HandoverParticipant,
    HandoverProtocol,
    HandoverRoom,
    HandoverSignature,
)

# Section name -> (model, foreign key columns that point to other sections, entity type for
# document links or None when the section holds no photos)
SECTIONS: dict[str, tuple[type[Any], dict[str, str], str | None]] = {
    "participants": (HandoverParticipant, {}, None),
    "meters": (HandoverMeter, {}, "handover_meter"),
    "rooms": (HandoverRoom, {}, "handover_room"),
    "defects": (HandoverDefect, {"room_id": "rooms"}, "handover_defect"),
    "keys": (HandoverKey, {}, None),
    "items": (HandoverItem, {}, "handover_item"),
    "notes": (HandoverNote, {}, None),
}
OUT_ROLES = ("moving_out", "seller", "handing_over")
IN_ROLES = ("moving_in", "buyer", "taking_over")
_IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def is_locked(protocol: HandoverProtocol) -> bool:
    return protocol.status in LOCKED_STATUSES


def is_finalized(protocol: HandoverProtocol) -> bool:
    return protocol.completed_at is not None and protocol.status != "cancelled"


def require_unlocked(protocol: HandoverProtocol) -> None:
    if is_locked(protocol):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Das Protokoll ist abgeschlossen und schreibgeschützt. "
            "Änderungen sind nur über eine neue Version möglich.",
        )


# Content lock after the first signature (M30-09, operator decision 28.09.2026) ---------------

# Protocol fields that stay editable while the content is locked: the step pointer and the
# internal fields, which are never part of the signed PDF.
CONTENT_FREE_FIELDS = frozenset(
    {"current_step", "internal_contact", "internal_note", "management_number"}
)


def valid_signatures(signatures: list[HandoverSignature]) -> list[HandoverSignature]:
    return [s for s in signatures if s.invalidated_at is None]


async def content_locked(session: AsyncSession, protocol: HandoverProtocol) -> bool:
    """True while at least one signature that has not been set aside exists on an open
    protocol: rooms, defects, meters, keys, items, notes, photos and the protocol fields of the
    PDF are then read only until "Änderung nach Unterschrift" records a reason."""
    if is_locked(protocol):
        return False
    found = await session.scalar(
        select(HandoverSignature.id)
        .where(
            HandoverSignature.protocol_id == protocol.id,
            HandoverSignature.invalidated_at.is_(None),
        )
        .limit(1)
    )
    return found is not None


async def require_content_unlocked(session: AsyncSession, protocol: HandoverProtocol) -> None:
    require_unlocked(protocol)
    if await content_locked(session, protocol):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Es liegt bereits eine Unterschrift vor, der Inhalt ist gesperrt. "
            "Änderungen sind nur über die Aktion Änderung nach Unterschrift mit "
            "Änderungsgrund möglich; alle Unterschriften müssen danach erneut geleistet werden.",
        )


async def record_change(
    session: AsyncSession,
    protocol: HandoverProtocol,
    *,
    reason: str,
    user_id: uuid.UUID | None,
    user_name: str | None,
) -> HandoverChange:
    """ "Änderung nach Unterschrift": records reason, time and user in the protocol history,
    marks every valid signature as given before the change and reopens the content. The
    signature rows and their files stay as evidence; each person has to sign again."""
    require_unlocked(protocol)
    if not await content_locked(session, protocol):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Es liegt keine gültige Unterschrift vor, der Inhalt ist nicht gesperrt.",
        )
    stamp = now()
    change = HandoverChange(
        tenant_id=protocol.tenant_id,
        protocol_id=protocol.id,
        reason=reason,
        changed_at=stamp,
        changed_by=user_id,
        changed_by_name=user_name,
        created_by=user_id,
    )
    session.add(change)
    await session.flush()
    rows = (
        await session.scalars(
            select(HandoverSignature).where(
                HandoverSignature.protocol_id == protocol.id,
                HandoverSignature.invalidated_at.is_(None),
            )
        )
    ).all()
    for sig in rows:
        sig.invalidated_at = stamp
        sig.invalidated_change_id = change.id
    change.signatures_invalidated = len(rows)
    if protocol.status == "signature_pending":
        protocol.status = "in_progress"
    protocol.updated_by = user_id
    await session.flush()
    return change


async def changes_of(session: AsyncSession, protocol_id: uuid.UUID) -> list[HandoverChange]:
    return list(
        (
            await session.scalars(
                select(HandoverChange)
                .where(HandoverChange.protocol_id == protocol_id)
                .order_by(HandoverChange.changed_at)
            )
        ).all()
    )


def iban_is_valid(iban: str) -> bool:
    """Formal IBAN check (mod 97). Empty input is accepted by the caller, never here."""
    value = iban.replace(" ", "").upper()
    if not _IBAN.fullmatch(value):
        return False
    rearranged = value[4:] + value[:4]
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    return int(numeric) % 97 == 1


async def protocol_number(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> str:
    """UP-JJJJMMTT-NNN: sequence per tenant and day (section 4.1, B04 style, gapless)."""
    stamp = today.strftime("%Y%m%d")
    value = await next_number(session, tenant_id, f"handover:{stamp}")
    return f"UP-{stamp}-{value:03d}"


def address_line(p: HandoverProtocol | dict[str, Any]) -> str:
    get = p.get if isinstance(p, dict) else lambda k: getattr(p, k, None)
    street = " ".join(x for x in (get("street"), get("house_number")) if x)
    place = " ".join(x for x in (get("postal_code"), get("city")) if x)
    return ", ".join(x for x in (street, place) if x)


async def prefill(session: AsyncSession, unit_id: uuid.UUID) -> dict[str, Any]:
    """Address snapshot from unit and property; the unit address wins when present."""
    from mhvp.properties.models import Property, Unit

    unit = await session.get(Unit, unit_id)
    if unit is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Einheit nicht gefunden.")
    prop = await session.get(Property, unit.property_id)
    out = {
        "property_id": unit.property_id,
        "unit_id": unit.id,
        "street": unit.street or (prop.street if prop else None),
        "house_number": unit.house_number or (prop.house_number if prop else None),
        "postal_code": unit.postal_code or (prop.postal_code if prop else None),
        "city": unit.city or (prop.city if prop else None),
        "object_label": prop.name if prop else None,
        "floor": unit.floor,
        "unit_number": unit.number,
        "unit_label": unit.label,
        "unit_position": unit.location,
    }
    return out


async def load_full(session: AsyncSession, protocol: HandoverProtocol) -> dict[str, Any]:
    out: dict[str, Any] = {"protocol": protocol}
    for name, (model, _, _) in SECTIONS.items():
        rows = await session.scalars(
            select(model)
            .where(model.protocol_id == protocol.id)
            .order_by(model.sort_order, model.created_at)
        )
        out[name] = list(rows.all())
    out["signatures"] = list(
        (
            await session.scalars(
                select(HandoverSignature)
                .where(HandoverSignature.protocol_id == protocol.id)
                .order_by(HandoverSignature.signed_at)
            )
        ).all()
    )
    out["documents"] = await documents_of(session, protocol.id)
    out["changes"] = await changes_of(session, protocol.id)
    return out


async def documents_of(session: AsyncSession, protocol_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every document linked to the protocol with its sub record link (section, item)."""
    rows = (
        await session.execute(
            select(Document, DocumentLink)
            .join(DocumentLink, DocumentLink.document_id == Document.id)
            .where(
                DocumentLink.entity_type == "handover_protocol",
                DocumentLink.entity_id == protocol_id,
            )
            .order_by(Document.created_at)
        )
    ).all()
    out = []
    for document, link in rows:
        # Sub record link of this protocol version (another version may link the same file).
        sub = None
        for candidate in (
            await session.scalars(
                select(DocumentLink).where(
                    DocumentLink.document_id == document.id,
                    DocumentLink.entity_type.in_(
                        ["handover_meter", "handover_room", "handover_defect", "handover_item"]
                    ),
                )
            )
        ).all():
            model = SECTIONS[candidate.entity_type.removeprefix("handover_") + "s"][0]
            row = await session.get(model, candidate.entity_id)
            if row is not None and row.protocol_id == protocol_id:
                sub = candidate
                break
        out.append(
            {
                "id": document.id,
                "title": document.title,
                "filename": document.filename,
                "mime_type": document.mime_type,
                "size": document.size,
                "sha256": document.sha256,
                "created_at": document.created_at,
                "role": link.role.value,
                "section": sub.entity_type.removeprefix("handover_") if sub else None,
                "item_id": sub.entity_id if sub else None,
                "kind": _document_kind(document, link, sub),
            }
        )
        # Derived preview (M30-08): rendered on the fly, never stored, no browser cache.
        out[-1]["thumbnail_url"] = (
            f"/api/v1/handover/protocols/{protocol_id}/documents/{document.id}/thumbnail"
            if is_thumbnail_source(out[-1])
            else None
        )
    return out


THUMBNAIL_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def is_thumbnail_source(document: dict[str, Any]) -> bool:
    """Photos of sub records and image attachments get a preview; signatures and PDFs not."""
    return document["kind"] in ("photo", "attachment") and (
        document["mime_type"] in THUMBNAIL_MIME_TYPES
    )


def _document_kind(document: Document, link: DocumentLink, sub: DocumentLink | None) -> str:
    if document.mime_type == "application/pdf" and link.role is LinkRole.GENERATED:
        return "pdf"
    if link.role is LinkRole.EVIDENCE and document.mime_type == "image/png" and sub is None:
        return "signature"
    if sub is not None or document.mime_type.startswith("image/"):
        return "photo"
    return "attachment"


HINT_TEXTS: dict[str, str] = {
    "no_address": "Für dieses Protokoll wurde keine Objektadresse angegeben.",
    "no_participants": "Es wurden keine beteiligten Personen erfasst.",
    "no_meters": "Es wurden keine Zählerstände erfasst.",
    "no_rooms": "Es wurden keine Räume erfasst.",
    "no_keys": "Es wurden keine Schlüssel erfasst.",
    "no_signature": "Es liegt keine Unterschrift vor.",
    "signatures_invalidated": "Nach einer Änderung nach Unterschrift wurde noch nicht erneut "
    "unterschrieben.",
    "no_date": "Das Übergabedatum fehlt.",
    "iban_invalid": "Die IBAN für die Kautionsrückzahlung erscheint formal ungültig.",
}


def completion_hint_codes(full: dict[str, Any]) -> list[str]:
    """Stable codes of the hints before completion (M31 WP2: the step bar marks the step from
    the code, never from the text). Same order as the texts."""
    p: HandoverProtocol = full["protocol"]
    codes = []
    if address_line(p) == "":
        codes.append("no_address")
    if not full["participants"]:
        codes.append("no_participants")
    if not full["meters"]:
        codes.append("no_meters")
    if not full["rooms"]:
        codes.append("no_rooms")
    if not full["keys"]:
        codes.append("no_keys")
    if not valid_signatures(full["signatures"]):
        codes.append("signatures_invalidated" if full["signatures"] else "no_signature")
    if p.handover_date is None:
        codes.append("no_date")
    if p.deposit_iban and not iban_is_valid(p.deposit_iban):
        codes.append("iban_invalid")
    return codes


def completion_hints(full: dict[str, Any]) -> list[str]:
    """Hints before completion; none of them blocks the completion (product decision)."""
    return [HINT_TEXTS[code] for code in completion_hint_codes(full)]


def party_roles(kind: str) -> tuple[str, str, str, str]:
    """Main roles per protocol kind: (out role, in role, out label, in label)."""
    if kind == "sale":
        return "seller", "buyer", "Verkaufender Eigentümer", "Kaufender Eigentümer"
    if kind == "general":
        return "handing_over", "taking_over", "Übergebende Partei", "Übernehmende Partei"
    return "moving_out", "moving_in", "Ausziehender Mieter", "Einziehender Mieter"


def role_label(role: str | None, kind: str) -> str:
    out_role, in_role, out_label, in_label = party_roles(kind)
    if role in (out_role, *OUT_ROLES):
        return out_label
    if role in (in_role, *IN_ROLES):
        return in_label
    return {
        "management": "Verwaltung",
        "broker": "Makler",
        "caretaker": "Hausmeister",
        "proxy": "Bevollmächtigter",
        "witness": "Zeuge",
        "relative": "Angehöriger",
        "expert": "Sachverständiger",
        "craftsman": "Handwerker",
    }.get(role or "", "Sonstige Person")


def _clone_row(model: type[Any], source: Any, overrides: dict[str, Any]) -> Any:
    data = {
        c.name: getattr(source, c.name)
        for c in source.__table__.columns
        if c.name not in ("id", "created_at", "updated_at", "created_by", "updated_by")
    }
    data.update(overrides)
    return model(**data)


async def create_version(
    session: AsyncSession,
    source: HandoverProtocol,
    *,
    reason: str,
    user_id: uuid.UUID | None,
) -> HandoverProtocol:
    """New editable version: every sub record is copied, documents are linked, not copied."""
    if not is_locked(source):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Eine neue Version ist nur für abgeschlossene Protokolle möglich.",
        )
    highest = await session.scalar(
        select(HandoverProtocol.version)
        .where(HandoverProtocol.number == source.number)
        .order_by(HandoverProtocol.version.desc())
        .limit(1)
    )
    new: HandoverProtocol = _clone_row(
        HandoverProtocol,
        source,
        {
            "version": int(highest or source.version) + 1,
            "parent_id": source.id,
            "change_reason": reason,
            "status": "in_progress",
            "current_step": "summary",
            "completed_at": None,
            "completed_by": None,
            "archived_at": None,
            "pdf_document_id": None,
            "pdf_sha256": None,
            "created_by": user_id,
            "updated_by": user_id,
        },
    )
    session.add(new)
    await session.flush()

    id_map: dict[str, dict[uuid.UUID, uuid.UUID]] = {name: {} for name in SECTIONS}
    full = await load_full(session, source)
    for name, (model, refs, entity_type) in SECTIONS.items():
        for row in full[name]:
            overrides: dict[str, Any] = {"protocol_id": new.id, "created_by": user_id}
            for column, target in refs.items():
                old = getattr(row, column)
                overrides[column] = id_map[target].get(old) if old else None
            copy = _clone_row(model, row, overrides)
            session.add(copy)
            await session.flush()
            id_map[name][row.id] = copy.id
            if entity_type is not None:
                await _relink(session, entity_type, row.id, copy.id, new)
    for sig in full["signatures"]:
        copy = _clone_row(
            HandoverSignature,
            sig,
            {
                "protocol_id": new.id,
                "participant_id": id_map["participants"].get(sig.participant_id)
                if sig.participant_id
                else None,
                "invalidated_change_id": None,
                "created_by": user_id,
            },
        )
        session.add(copy)
    # Protocol level links (attachments, signatures, photos) point to the new version too.
    links = (
        await session.scalars(
            select(DocumentLink).where(
                DocumentLink.entity_type == "handover_protocol",
                DocumentLink.entity_id == source.id,
                DocumentLink.role != LinkRole.GENERATED,  # the old PDF stays with its version
            )
        )
    ).all()
    for link in links:
        session.add(
            DocumentLink(
                tenant_id=link.tenant_id,
                document_id=link.document_id,
                entity_type="handover_protocol",
                entity_id=new.id,
                role=link.role,
            )
        )
    await session.flush()
    return new


async def _relink(
    session: AsyncSession,
    entity_type: str,
    old_id: uuid.UUID,
    new_id: uuid.UUID,
    new: HandoverProtocol,
) -> None:
    links = (
        await session.scalars(
            select(DocumentLink).where(
                DocumentLink.entity_type == entity_type, DocumentLink.entity_id == old_id
            )
        )
    ).all()
    for link in links:
        session.add(
            DocumentLink(
                tenant_id=new.tenant_id,
                document_id=link.document_id,
                entity_type=entity_type,
                entity_id=new_id,
                role=link.role,
            )
        )


async def store_pdf(
    session: AsyncSession,
    blobs: Any,
    protocol: HandoverProtocol,
    pdf: bytes,
    *,
    user_id: uuid.UUID | None,
) -> Document:
    from mhvp.documents.services import store_document

    links: list[tuple[str, uuid.UUID, LinkRole]] = [
        ("handover_protocol", protocol.id, LinkRole.GENERATED)
    ]
    if protocol.unit_id:
        links.append(("unit", protocol.unit_id, LinkRole.GENERATED))
    elif protocol.property_id:
        links.append(("property", protocol.property_id, LinkRole.GENERATED))
    document = await store_document(
        session,
        blobs,
        tenant_id=protocol.tenant_id,
        data=pdf,
        title=f"Übergabeprotokoll {protocol.number}"
        + (f" Version {protocol.version}" if protocol.version > 1 else ""),
        filename=pdf_filename(protocol),
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=links,
        created_by=user_id,
        visibility=["tenant"],
    )
    protocol.pdf_document_id = document.id
    protocol.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
    return document


def pdf_filename(protocol: HandoverProtocol) -> str:
    def slug(value: str | None) -> str:
        text = (value or "").translate(
            {ord("ä"): "ae", ord("ö"): "oe", ord("ü"): "ue", ord("ß"): "ss"}
        )
        text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
        return text[:40]

    parts = ["U-Protokoll", protocol.number]
    if protocol.version > 1:
        parts.append(f"V{protocol.version}")
    for value in (
        " ".join(x for x in (protocol.street, protocol.house_number) if x),
        protocol.city,
    ):
        if slug(value):
            parts.append(slug(value))
    if protocol.handover_date:
        parts.append(protocol.handover_date.isoformat())
    return "_".join(parts) + ".pdf"


def now() -> datetime:
    return datetime.now(UTC)


# Zählerstände übernehmen (Package F, handbook Mieterwechsel step 2) --------------------------


def _normalised_number(value: str | None) -> str:
    return re.sub(r"[\s\-_/.]", "", value or "").casefold()


async def transfer_meter_readings(
    session: AsyncSession, protocol: HandoverProtocol, actor: uuid.UUID | None
) -> dict[str, Any]:
    """Creates one ``meter_reading`` (source ``manual``, note with the protocol number) per
    protocol meter row that is not yet taken over and can be matched to a meter of the
    protocol's unit (or the property's common meters).

    Matching: ``meter_id`` when the row carries one, else the meter number (whitespace,
    dashes, dots and slashes ignored, case insensitive) among the meters of the unit and the
    common meters of the property. Rows without value, without matchable meter or with an
    ambiguous number are reported as skipped and left untouched. The reading date is the
    row's ``read_on``, else the handover date; without either the row is skipped. The link
    ``handover_meter.meter_reading_id`` makes a second call a no-op for those rows.
    """
    from mhvp.properties.models import Meter, MeterReading, ReadingSource

    rows = list(
        (
            await session.scalars(
                select(HandoverMeter)
                .where(HandoverMeter.protocol_id == protocol.id)
                .order_by(HandoverMeter.sort_order, HandoverMeter.created_at)
            )
        ).all()
    )
    candidates: list[Meter] = []
    if protocol.property_id is not None:
        query = select(Meter).where(Meter.property_id == protocol.property_id)
        if protocol.unit_id is not None:
            query = query.where((Meter.unit_id == protocol.unit_id) | (Meter.unit_id.is_(None)))
        else:
            query = query.where(Meter.unit_id.is_(None))
        candidates = list((await session.scalars(query.order_by(Meter.number))).all())
    by_id = {m.id: m for m in candidates}
    by_number: dict[str, list[Meter]] = {}
    for m in candidates:
        by_number.setdefault(_normalised_number(m.number), []).append(m)

    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    already: list[dict[str, Any]] = []
    for row in rows:
        label = row.custom_type or row.meter_type or ""
        item = {"item_id": row.id, "number": row.number, "meter_type": label}
        if row.meter_reading_id is not None:
            already.append({**item, "meter_reading_id": row.meter_reading_id})
            continue
        if row.value is None:
            skipped.append({**item, "reason": "no_value"})
            continue
        day = row.read_on or protocol.handover_date
        if day is None:
            skipped.append({**item, "reason": "no_date"})
            continue
        meter: Meter | None = None
        if row.meter_id is not None:
            meter = by_id.get(row.meter_id)
            if meter is None:
                skipped.append({**item, "reason": "meter_not_in_unit"})
                continue
        else:
            key = _normalised_number(row.number)
            matches = by_number.get(key, []) if key else []
            if len(matches) == 1:
                meter = matches[0]
            elif len(matches) > 1:
                skipped.append({**item, "reason": "ambiguous_number"})
                continue
            else:
                skipped.append({**item, "reason": "no_meter"})
                continue
        reading = MeterReading(
            tenant_id=protocol.tenant_id,
            meter_id=meter.id,
            read_at=day,
            value=row.value,
            source=ReadingSource.MANUAL,
            notes=f"Übergabeprotokoll {protocol.number}",
            created_by=actor,
        )
        session.add(reading)
        await session.flush()
        # Only the takeover link is written to the protocol row. The resolved meter is
        # recorded on the row while the protocol is still open; a completed protocol is
        # locked and its content (including ``meter_id``) stays as signed.
        row.meter_reading_id = reading.id
        if not is_locked(protocol):
            row.meter_id = meter.id
            row.updated_by = actor
        created.append(
            {
                **item,
                "meter_id": meter.id,
                "meter_number": meter.number,
                "meter_reading_id": reading.id,
                "read_at": day,
                "value": row.value,
            }
        )
    await session.flush()
    return {"created": created, "skipped": skipped, "already_transferred": already}
