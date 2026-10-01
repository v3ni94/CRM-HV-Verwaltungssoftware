"""Consent checks per processing purpose (AC06, GA02-06, rule AC06-einwilligungen).

Each consent kind of 6.1 gates one processing step:

* ``marketing``: serial dispatch flagged as advertising reaches only contacts with a valid
  marketing consent; mandatory communication (statements, dunning, invitations) is never
  gated here.
* ``email_delivery``: documents go by e-mail only with a valid consent, or when the tenant
  policy accepts a contractual agreement; otherwise the dispatch falls back to post.
* ``portal_terms``: once the tenant has published a terms version, activation and access
  need a valid acceptance of exactly that version.
* ``data_sharing``: passing contact data to service providers needs a valid consent unless
  the tenant policy accepts contractual necessity.

The legal classification of each purpose is an open decision (OPEN_QUESTIONS AC06-01 to
AC06-03): the defaults are the restrictive variant, the tenant policy only widens them.
A consent is valid when ``granted_at`` is not in the future and it is not revoked."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Consent, ConsentKind

POLICY_KEY = "consent_policy"
TERMS_SOURCE_PREFIX = "portal_terms_version="

EmailDeliveryMode = Literal["consent_only", "consent_or_contract"]
DataSharingMode = Literal["consent_only", "consent_or_contract"]


@dataclass(frozen=True)
class ConsentPolicy:
    """Per tenant switches (``tenant_settings.sources["consent_policy"]``)."""

    email_delivery: EmailDeliveryMode = "consent_only"
    data_sharing: DataSharingMode = "consent_only"
    portal_terms_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "email_delivery": self.email_delivery,
            "data_sharing": self.data_sharing,
            "portal_terms_version": self.portal_terms_version,
        }


def policy_from(sources: dict[str, Any] | None) -> ConsentPolicy:
    raw = (sources or {}).get(POLICY_KEY) or {}
    if not isinstance(raw, dict):
        return ConsentPolicy()
    email = raw.get("email_delivery")
    sharing = raw.get("data_sharing")
    version = raw.get("portal_terms_version")
    return ConsentPolicy(
        email_delivery=email
        if email in ("consent_only", "consent_or_contract")
        else "consent_only",
        data_sharing=sharing
        if sharing in ("consent_only", "consent_or_contract")
        else "consent_only",
        portal_terms_version=version if isinstance(version, str) and version.strip() else None,
    )


async def load_policy(session: AsyncSession) -> ConsentPolicy:
    """Policy of the tenant of the current RLS session."""
    from mhvp.platform.models import TenantSettings

    return policy_from(await session.scalar(select(TenantSettings.sources)))


def _valid(now: datetime) -> Any:
    return (Consent.granted_at <= now, or_(Consent.revoked_at.is_(None), Consent.revoked_at > now))


async def has_consent(
    session: AsyncSession,
    contact_id: uuid.UUID,
    kind: ConsentKind,
    *,
    at: datetime | None = None,
    source_equals: str | None = None,
) -> bool:
    now = at or datetime.now(UTC)
    stmt = select(Consent.id).where(
        Consent.contact_id == contact_id, Consent.kind == kind, *_valid(now)
    )
    if source_equals is not None:
        stmt = stmt.where(Consent.source == source_equals)
    return await session.scalar(stmt.limit(1)) is not None


async def contacts_with_consent(
    session: AsyncSession, contact_ids: list[uuid.UUID], kind: ConsentKind
) -> set[uuid.UUID]:
    if not contact_ids:
        return set()
    now = datetime.now(UTC)
    rows = await session.scalars(
        select(Consent.contact_id).where(
            Consent.contact_id.in_(contact_ids), Consent.kind == kind, *_valid(now)
        )
    )
    return set(rows.all())


def terms_source(version: str) -> str:
    """``consent.source`` of a portal terms acceptance; it carries the accepted version."""
    return f"{TERMS_SOURCE_PREFIX}{version}"[:200]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


async def email_delivery_decision(
    session: AsyncSession, contact_id: uuid.UUID, policy: ConsentPolicy | None = None
) -> Decision:
    policy = policy or await load_policy(session)
    if await has_consent(session, contact_id, ConsentKind.EMAIL_DELIVERY):
        return Decision(True, "email_delivery_consent")
    if policy.email_delivery == "consent_or_contract":
        return Decision(True, "tenant_policy_contract")
    return Decision(False, "email_delivery_consent_missing")


async def data_sharing_decision(
    session: AsyncSession,
    contact_id: uuid.UUID,
    *,
    contractual_necessity: bool = False,
    policy: ConsentPolicy | None = None,
) -> Decision:
    """Check at every place that passes contact data to a third party (work order, webhook).
    ``contractual_necessity`` is the caller's statement that the transfer serves the contract
    (for example the tenant's phone number on a repair order); it counts only when the tenant
    policy accepts it."""
    policy = policy or await load_policy(session)
    if await has_consent(session, contact_id, ConsentKind.DATA_SHARING):
        return Decision(True, "data_sharing_consent")
    if contractual_necessity and policy.data_sharing == "consent_or_contract":
        return Decision(True, "tenant_policy_contract")
    return Decision(False, "data_sharing_consent_missing")


async def portal_terms_decision(
    session: AsyncSession, contact_id: uuid.UUID, policy: ConsentPolicy | None = None
) -> Decision:
    policy = policy or await load_policy(session)
    if policy.portal_terms_version is None:
        return Decision(True, "no_terms_published")
    if await has_consent(
        session,
        contact_id,
        ConsentKind.PORTAL_TERMS,
        source_equals=terms_source(policy.portal_terms_version),
    ):
        return Decision(True, "portal_terms_accepted")
    return Decision(False, "portal_terms_missing")
