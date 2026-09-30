"""Named portal roles (3.4, S16-10), derived from relations, never assigned by hand.

Section 3.4: ``tenant_resident`` (Mieter), ``owner`` (Eigentümer), ``board_member`` (Beirat,
in addition to owner), ``service_provider`` (Dienstleister), derived from contracts and service
provider relations. This module holds the names and the pure derivation rule; the portal
domain supplies the facts from its data (rental contracts, ownerships, board seats, service
provider relations) at the cut-off date it uses.

Rule (Fachliche Umsetzung of 3.4): a board seat without an ownership yields no role
(``board_member`` only in addition to ``owner``); no relation yields no role.
"""

from dataclasses import dataclass
from enum import StrEnum


class PortalRole(StrEnum):
    TENANT_RESIDENT = "tenant_resident"
    OWNER = "owner"
    BOARD_MEMBER = "board_member"
    SERVICE_PROVIDER = "service_provider"


@dataclass(frozen=True, slots=True)
class PortalRelations:
    active_rental_contracts: int = 0
    active_ownerships: int = 0
    board_seats: int = 0
    service_provider_relations: int = 0


def derive_portal_roles(relations: PortalRelations) -> tuple[PortalRole, ...]:
    roles: list[PortalRole] = []
    if relations.active_rental_contracts > 0:
        roles.append(PortalRole.TENANT_RESIDENT)
    if relations.active_ownerships > 0:
        roles.append(PortalRole.OWNER)
        if relations.board_seats > 0:
            roles.append(PortalRole.BOARD_MEMBER)
    if relations.service_provider_relations > 0:
        roles.append(PortalRole.SERVICE_PROVIDER)
    return tuple(roles)
