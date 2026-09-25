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
    return out


def _document_kind(document: Document, link: DocumentLink, sub: DocumentLink | None) -> str:
    if document.mime_type == "application/pdf" and link.role is LinkRole.GENERATED:
        return "pdf"
    if link.role is LinkRole.EVIDENCE and document.mime_type == "image/png" and sub is None:
        return "signature"
    if sub is not None or document.mime_type.startswith("image/"):
        return "photo"
    return "attachment"


def completion_hints(full: dict[str, Any]) -> list[str]:
    """Hints before completion; none of them blocks the completion (product decision)."""
    p: HandoverProtocol = full["protocol"]
    hints = []
    if address_line(p) == "":
        hints.append("Für dieses Protokoll wurde keine Objektadresse angegeben.")
    if not full["participants"]:
        hints.append("Es wurden keine beteiligten Personen erfasst.")
    if not full["meters"]:
        hints.append("Es wurden keine Zählerstände erfasst.")
    if not full["rooms"]:
        hints.append("Es wurden keine Räume erfasst.")
    if not full["keys"]:
        hints.append("Es wurden keine Schlüssel erfasst.")
    if not full["signatures"]:
        hints.append("Es liegt keine Unterschrift vor.")
    if p.handover_date is None:
        hints.append("Das Übergabedatum fehlt.")
    if p.deposit_iban and not iban_is_valid(p.deposit_iban):
        hints.append("Die IBAN für die Kautionsrückzahlung erscheint formal ungültig.")
    return hints


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
