"""Portal feature switches per tenant and representation helpers (M21-08, M21-05).

The switches are a Produktschutz configuration, not a legal rule: every switch is off until the
management turns it on. Turning one on never opens a gate: the AI pre-qualification still needs
the approved AI provider with data processing agreement (see ``mhvp.portal.chat``) and the
support view still needs the consent of the portal user (see ``mhvp.portal.support``)."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.portal.models import PortalAccount, PortalFeatureSetting, PortalRepresentation
from mhvp.workspace.services import local_today

FEATURES = (
    "chat_enabled",
    "chat_ai_prequalification_enabled",
    "support_login_enabled",
    "owner_rental_income_enabled",
    "owner_rental_statements_enabled",
    "chat_bot_enabled",
    "privacy_feature_enabled",
    "tenant_statement_enabled",
    "portal_owner_receipts_enabled",
    "owner_hoa_rental_statements_enabled",
)
OWNER_TICKET_SCOPES = ("none", "released", "property")
# AE30 (AA14-02): off keeps the ratings of service providers internal (default), staff shows
# them aggregated to the management only. Publication to providers or third parties is not
# offered (data protection, decision AA14-02 open).
PROVIDER_RATING_MODES = ("off", "staff", "all")


async def get_or_default(session: AsyncSession) -> PortalFeatureSetting:
    """The tenant's row (RLS scoped) or an unsaved object with all switches off."""
    row = await session.scalar(select(PortalFeatureSetting))
    if row is not None:
        return row
    return PortalFeatureSetting(
        chat_enabled=False,
        chat_ai_prequalification_enabled=False,
        support_login_enabled=False,
        owner_rental_income_enabled=False,
        owner_rental_statements_enabled=False,
        chat_bot_enabled=False,
        privacy_feature_enabled=False,
        tenant_statement_enabled=False,
        portal_owner_receipts_enabled=False,
        owner_hoa_rental_statements_enabled=False,
        owner_ticket_scope="released",
        provider_rating_display="off",
    )


def feature_dict(row: PortalFeatureSetting) -> dict[str, Any]:
    out: dict[str, Any] = {name: bool(getattr(row, name)) for name in FEATURES}
    out["owner_ticket_scope"] = row.owner_ticket_scope or "released"
    return out


def admin_feature_dict(row: PortalFeatureSetting) -> dict[str, Any]:
    """Switches for the portal administration: ``feature_dict`` plus the management only
    switches that the portal itself must not see (AE30)."""
    out = feature_dict(row)
    out["provider_rating_display"] = row.provider_rating_display or "off"
    return out


def _active(rep: PortalRepresentation, today: date) -> bool:
    return rep_state(rep, today) == "active"


def rep_state(rep: PortalRepresentation, today: date) -> str:
    """Display state of a power of attorney (M21-05): revoked, pending (not yet valid), expired
    (valid_to passed) or active. Access follows ``valid_from``/``valid_to`` of the grants."""
    if rep.status != "active":
        return "revoked"
    if rep.valid_from > today:
        return "pending"
    if rep.valid_to is not None and rep.valid_to < today:
        return "expired"
    return "active"


def _principal_label(contact: Any) -> str | None:
    if contact is None:
        return None
    name = " ".join(p for p in (contact.first_name, contact.last_name) if p)
    return name or contact.company_name or contact.display_name


async def own_representations(
    session: AsyncSession, account: PortalAccount, today: date | None = None
) -> list[dict[str, Any]]:
    """All powers of attorney held by the account with state, principal name and the days until
    expiry (None without end date). Only the name of the principal and the period are shown,
    never the document or other data of the principal."""
    from mhvp.contacts.models import Contact

    today = today or local_today()
    rows = (
        await session.scalars(
            select(PortalRepresentation)
            .where(PortalRepresentation.account_id == account.id)
            .order_by(PortalRepresentation.valid_from.desc())
        )
    ).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        contact = await session.get(Contact, r.principal_contact_id)
        state = rep_state(r, today)
        out.append(
            {
                "id": r.id,
                "principal_contact_id": r.principal_contact_id,
                "principal_name": _principal_label(contact),
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
                "state": state,
                "expires_in_days": (r.valid_to - today).days
                if state == "active" and r.valid_to is not None
                else None,
            }
        )
    return out


async def active_representations(
    session: AsyncSession, account: PortalAccount
) -> list[dict[str, Any]]:
    return [r for r in await own_representations(session, account) if r["state"] == "active"]
