"""Person match against the address book in the property onboarding (10.2 step 4, M7-02).

Signals: IBAN (keyed fingerprint), e-mail, name similarity and address. Thresholds are per
tenant (``OnboardingMatchSetting``). A hit at or above ``link_threshold`` is linked, between
``suggest_threshold`` and ``link_threshold`` only proposed, below it a new incomplete contact
is created. The match is a proposal; nothing here writes contacts.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import OnboardingMatchSetting
from mhvp.contacts.models import Contact, ContactAddress, ContactBankAccount, ContactEmail
from mhvp.contacts.validation import normalise_iban
from mhvp.core import crypto

DEFAULT_LINK = Decimal("0.90")
DEFAULT_SUGGEST = Decimal("0.60")
POSTAL_BONUS = 0.15
STREET_BONUS = 0.10
EMAIL_SCORE = 0.95
IBAN_SCORE = 1.0


@dataclass
class MatchCandidate:
    contact_id: uuid.UUID
    name: str
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    decision: str  # link | suggest | none
    candidates: list[MatchCandidate]

    @property
    def best(self) -> MatchCandidate | None:
        return self.candidates[0] if self.candidates else None


def classify(score: float, link: Decimal, suggest: Decimal) -> str:
    if Decimal(str(score)) >= link:
        return "link"
    if Decimal(str(score)) >= suggest:
        return "suggest"
    return "none"


def combine(
    *, iban: bool, email: bool, name_similarity: float, postal: bool, street: bool
) -> tuple[float, list[str]]:
    """Highest single hard signal wins; name similarity is raised by address agreement."""
    scores: list[tuple[float, str]] = []
    if iban:
        scores.append((IBAN_SCORE, "gleiche IBAN"))
    if email:
        scores.append((EMAIL_SCORE, "gleiche E-Mail-Adresse"))
    if name_similarity > 0:
        value = name_similarity
        reasons = ["ähnlicher Name"]
        if postal:
            value += POSTAL_BONUS
            reasons.append("gleiche Postleitzahl")
        if street:
            value += STREET_BONUS
            reasons.append("gleiche Straße")
        scores.append((min(value, 0.99), ", ".join(reasons)))
    if not scores:
        return 0.0, []
    best = max(scores, key=lambda item: item[0])
    return best[0], [best[1]]


async def load_thresholds(session: AsyncSession) -> tuple[Decimal, Decimal]:
    row = await session.scalar(select(OnboardingMatchSetting))
    if row is None:
        return DEFAULT_LINK, DEFAULT_SUGGEST
    return row.link_threshold, row.suggest_threshold


async def match_person(
    session: AsyncSession, data: dict[str, Any], *, limit: int = 3
) -> MatchResult:
    """``data`` keys (all optional): first_name, last_name, company_name, email, iban,
    postal_code, street. Reads run inside the tenant transaction (RLS)."""
    link, suggest = await load_thresholds(session)
    name = (
        " ".join(
            p
            for p in (data.get("last_name"), data.get("first_name"), data.get("company_name"))
            if p
        )
        .strip()
        .lower()
    )
    signals: dict[uuid.UUID, dict[str, Any]] = {}

    def sig(contact_id: uuid.UUID) -> dict[str, Any]:
        return signals.setdefault(
            contact_id,
            {"iban": False, "email": False, "name": 0.0, "postal": False, "street": False},
        )

    if data.get("iban"):
        try:
            print_ = crypto.fingerprint(normalise_iban(str(data["iban"])))
        except ValueError:
            print_ = None
        if print_:
            for (cid,) in (
                await session.execute(
                    select(ContactBankAccount.contact_id).where(
                        ContactBankAccount.iban_fingerprint == print_
                    )
                )
            ).all():
                sig(cid)["iban"] = True
    if data.get("email"):
        for (cid,) in (
            await session.execute(
                select(ContactEmail.contact_id).where(
                    ContactEmail.email == str(data["email"]).strip().lower()
                )
            )
        ).all():
            sig(cid)["email"] = True
    if len(name) >= 3:
        similarity = func.similarity(func.lower(Contact.search_text), name)
        rows = (
            await session.execute(
                select(Contact.id, similarity.label("s"))
                .where(Contact.deleted_at.is_(None), similarity > 0.3)
                .order_by(similarity.desc())
                .limit(10)
            )
        ).all()
        for row in rows:
            sig(row.id)["name"] = float(row.s)
    if signals and (data.get("postal_code") or data.get("street")):
        addresses = (
            await session.scalars(
                select(ContactAddress).where(ContactAddress.contact_id.in_(list(signals)))
            )
        ).all()
        street = (data.get("street") or "").strip().lower()
        for address in addresses:
            entry = sig(address.contact_id)
            if data.get("postal_code") and address.postal_code == data["postal_code"]:
                entry["postal"] = True
            if street and (address.street or "").strip().lower() == street:
                entry["street"] = True
    if not signals:
        return MatchResult("none", [])
    contacts = {
        c.id: c
        for c in (
            await session.scalars(
                select(Contact).where(Contact.id.in_(list(signals)), Contact.deleted_at.is_(None))
            )
        ).all()
    }
    candidates = []
    for cid, entry in signals.items():
        contact = contacts.get(cid)
        if contact is None:
            continue
        score, reasons = combine(
            iban=entry["iban"],
            email=entry["email"],
            name_similarity=entry["name"],
            postal=entry["postal"],
            street=entry["street"],
        )
        if score >= float(suggest):
            candidates.append(MatchCandidate(cid, contact.display_name, score, reasons))
    candidates.sort(key=lambda c: (-c.score, c.name))
    candidates = candidates[:limit]
    if not candidates:
        return MatchResult("none", [])
    return MatchResult(classify(candidates[0].score, link, suggest), candidates)
