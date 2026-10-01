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
A consent is valid when ``granted_at`` is not in the future and it is not revoked.

AE34: the tenant maintains the legal basis per processing (register
``tenant_settings.sources["consent_legal_basis"]``): ``consent`` (default, a valid consent
of the contact is needed), ``contract`` (covered by the contract, no consent per recipient) or
``legitimate_interest`` (no consent, but an objection of the contact blocks the processing).
Which basis is tenable per purpose is an operator decision with legal advice; the register
only records the choice with its justification and the checks follow it. The legacy switches
``consent_policy.email_delivery`` and ``data_sharing`` (``consent_or_contract``) count as basis
``contract`` as long as the register has no entry for the purpose."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Consent, ConsentKind

POLICY_KEY = "consent_policy"
LEGAL_BASIS_KEY = "consent_legal_basis"
TERMS_SOURCE_PREFIX = "portal_terms_version="

EmailDeliveryMode = Literal["consent_only", "consent_or_contract"]
DataSharingMode = Literal["consent_only", "consent_or_contract"]

PURPOSES: tuple[str, ...] = ("email_delivery", "data_sharing", "marketing", "portal_terms")
BASES: tuple[str, ...] = ("consent", "contract", "legitimate_interest")
# Technically offered variants per purpose; whether one is tenable is the operator's decision
# (OPEN_QUESTIONS AC06-01 to AC06-03, AE34-01). Advertising is never covered by "contract".
ALLOWED_BASES: dict[str, tuple[str, ...]] = {
    "email_delivery": ("consent", "contract", "legitimate_interest"),
    "data_sharing": ("consent", "contract", "legitimate_interest"),
    "marketing": ("consent", "legitimate_interest"),
    "portal_terms": ("consent", "contract"),
}
OBJECTION_KINDS = (ConsentKind.EMAIL_DELIVERY, ConsentKind.DATA_SHARING, ConsentKind.MARKETING)
_PURPOSE_KIND = {
    "email_delivery": ConsentKind.EMAIL_DELIVERY,
    "data_sharing": ConsentKind.DATA_SHARING,
    "marketing": ConsentKind.MARKETING,
    "portal_terms": ConsentKind.PORTAL_TERMS,
}
MIN_NOTE_LENGTH = 10


@dataclass(frozen=True)
class BasisEntry:
    """One register entry: the chosen basis and why (for example the contract clause or the
    documented balancing of interests)."""

    basis: str
    note: str | None = None
    set_at: str | None = None
    set_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "note": self.note,
            "set_at": self.set_at,
            "set_by": self.set_by,
        }


@dataclass(frozen=True)
class ConsentPolicy:
    """Per tenant switches (``tenant_settings.sources["consent_policy"]``) plus the legal
    basis register (``sources["consent_legal_basis"]``)."""

    email_delivery: EmailDeliveryMode = "consent_only"
    data_sharing: DataSharingMode = "consent_only"
    portal_terms_version: str | None = None
    legal_basis: dict[str, BasisEntry] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "email_delivery": self.email_delivery,
            "data_sharing": self.data_sharing,
            "portal_terms_version": self.portal_terms_version,
        }

    def basis_for(self, purpose: str) -> str:
        """Effective basis: register entry, else the legacy switch, else ``consent``."""
        entry = self.legal_basis.get(purpose)
        if entry is not None:
            return entry.basis
        if purpose == "email_delivery" and self.email_delivery == "consent_or_contract":
            return "contract"
        if purpose == "data_sharing" and self.data_sharing == "consent_or_contract":
            return "contract"
        return "consent"

    def basis_origin(self, purpose: str) -> str:
        if purpose in self.legal_basis:
            return "register"
        if self.basis_for(purpose) != "consent":
            return "policy"
        return "default"


def validate_basis(purpose: str, basis: str, note: str | None) -> str | None:
    """Returns a German error text or ``None``. A basis other than ``consent`` needs a
    justification so that the choice is traceable (accountability, rule 0.1.13)."""
    if purpose not in PURPOSES:
        return "Unbekannter Verarbeitungszweck."
    if basis not in ALLOWED_BASES[purpose]:
        return "Diese Rechtsgrundlage ist für diesen Verarbeitungszweck nicht vorgesehen."
    if basis != "consent" and len((note or "").strip()) < MIN_NOTE_LENGTH:
        return "Bitte die Begründung der Rechtsgrundlage angeben (mindestens 10 Zeichen)."
    return None


def policy_from(sources: dict[str, Any] | None) -> ConsentPolicy:
    legal_basis = _register_from(sources)
    raw = (sources or {}).get(POLICY_KEY) or {}
    if not isinstance(raw, dict):
        return ConsentPolicy(legal_basis=legal_basis)
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
        legal_basis=legal_basis,
    )


def _register_from(sources: dict[str, Any] | None) -> dict[str, BasisEntry]:
    raw = (sources or {}).get(LEGAL_BASIS_KEY)
    out: dict[str, BasisEntry] = {}
    if not isinstance(raw, dict):
        return out
    for purpose, value in raw.items():
        if purpose not in PURPOSES or not isinstance(value, dict):
            continue
        basis = value.get("basis")
        if basis not in ALLOWED_BASES[purpose]:
            continue  # an invalid stored value falls back to the restrictive default
        note = value.get("note")
        out[purpose] = BasisEntry(
            basis=basis,
            note=note if isinstance(note, str) else None,
            set_at=value.get("set_at") if isinstance(value.get("set_at"), str) else None,
            set_by=value.get("set_by") if isinstance(value.get("set_by"), str) else None,
        )
    return out


def register_value(
    sources: dict[str, Any] | None,
    purpose: str,
    entry: BasisEntry,
) -> dict[str, Any]:
    """New value of ``sources["consent_legal_basis"]`` with ``purpose`` replaced."""
    current = (sources or {}).get(LEGAL_BASIS_KEY)
    value: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    value[purpose] = entry.as_dict()
    return value


def purpose_kind(purpose: str) -> ConsentKind:
    return _PURPOSE_KIND[purpose]


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
        Consent.contact_id == contact_id,
        Consent.kind == kind,
        Consent.record_type == "consent",
        *_valid(now),
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
            Consent.contact_id.in_(contact_ids),
            Consent.kind == kind,
            Consent.record_type == "consent",
            *_valid(now),
        )
    )
    return set(rows.all())


async def objected_contacts(
    session: AsyncSession, contact_ids: list[uuid.UUID], kind: ConsentKind
) -> set[uuid.UUID]:
    """Contacts that object to a processing based on legitimate interest (AE34): a valid
    objection record, or a consent of this kind that was revoked (a revocation is read as the
    wish not to be contacted this way; a new valid consent lifts it because the consent is
    checked first by every caller)."""
    if not contact_ids:
        return set()
    now = datetime.now(UTC)
    rows = await session.scalars(
        select(Consent.contact_id).where(
            Consent.contact_id.in_(contact_ids),
            Consent.kind == kind,
            or_(
                and_(Consent.record_type == "objection", *_valid(now)),
                and_(
                    Consent.record_type == "consent",
                    Consent.revoked_at.is_not(None),
                    Consent.revoked_at <= now,
                ),
            ),
        )
    )
    return set(rows.all())


async def marketing_permitted(
    session: AsyncSession,
    contact_ids: list[uuid.UUID],
    policy: ConsentPolicy | None = None,
) -> set[uuid.UUID]:
    """Contacts an advertising dispatch may reach: basis ``consent`` needs a valid marketing
    consent, basis ``legitimate_interest`` reaches everyone without objection or revoked
    consent (AE34)."""
    policy = policy or await load_policy(session)
    with_consent = await contacts_with_consent(session, contact_ids, ConsentKind.MARKETING)
    if policy.basis_for("marketing") != "legitimate_interest":
        return with_consent
    objected = await objected_contacts(session, contact_ids, ConsentKind.MARKETING)
    return with_consent | (set(contact_ids) - objected)


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
    basis = policy.basis_for("email_delivery")
    if basis == "contract":
        return Decision(True, "tenant_policy_contract")
    if basis == "legitimate_interest":
        if await objected_contacts(session, [contact_id], ConsentKind.EMAIL_DELIVERY):
            return Decision(False, "email_delivery_objection_recorded")
        return Decision(True, "legitimate_interest")
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
    basis = policy.basis_for("data_sharing")
    if contractual_necessity and basis == "contract":
        return Decision(True, "tenant_policy_contract")
    if basis == "legitimate_interest":
        if await objected_contacts(session, [contact_id], ConsentKind.DATA_SHARING):
            return Decision(False, "data_sharing_objection_recorded")
        return Decision(True, "legitimate_interest")
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
