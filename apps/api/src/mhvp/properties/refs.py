"""Compact property references for ``include`` on lists of other domains (S12-03, Q12)."""

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.scope import session_allowed_property_ids
from mhvp.properties.models import LegalEntity, Property, PropertyOwner


def property_ref(p: Property) -> dict[str, Any]:
    return {
        "id": p.id,
        "number": p.number,
        "name": p.name,
        "street": p.street,
        "house_number": p.house_number,
        "postal_code": p.postal_code,
        "city": p.city,
    }


async def property_refs(
    session: AsyncSession, ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Properties by id; ids outside the membership's property assignment (M2-02) are left
    out, so an include never discloses a property the caller may not see."""
    wanted = {i for i in ids if i is not None}
    allowed = session_allowed_property_ids(session)
    if allowed is not None:
        wanted &= set(allowed)
    if not wanted:
        return {}
    rows = await session.scalars(select(Property).where(Property.id.in_(wanted)))
    return {p.id: property_ref(p) for p in rows.all()}


async def legal_entity_refs_by_property(
    session: AsyncSession, property_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Legal entities of each property (6.9.1): the entity bound to the property (WEG) and the
    entities of its recorded owners (Mietverwaltung), each once, ordered by name."""
    ids = set(property_ids)
    out: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    if not ids:
        return out
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    direct = await session.execute(
        select(LegalEntity.property_id, LegalEntity).where(LegalEntity.property_id.in_(ids))
    )
    via_owner = await session.execute(
        select(PropertyOwner.property_id, LegalEntity)
        .join(LegalEntity, LegalEntity.party_id == PropertyOwner.party_id)
        .where(PropertyOwner.property_id.in_(ids))
    )
    pairs: list[tuple[uuid.UUID | None, LegalEntity]] = [
        (r[0], r[1]) for r in [*direct.tuples().all(), *via_owner.tuples().all()]
    ]
    pairs.sort(key=lambda r: (r[1].name, str(r[1].id)))
    for prop_id, le in pairs:
        if prop_id is None or (prop_id, le.id) in seen:
            continue
        seen.add((prop_id, le.id))
        out[prop_id].append(
            {"id": le.id, "kind": le.kind, "name": le.name, "party_id": le.party_id}
        )
    return out
