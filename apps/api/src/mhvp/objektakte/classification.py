"""M35 Stufe 3, rule stage (docs/plans/M35-objektakte-uebernahme.md section 4 item 1, Stufe 1
of the three stage classification carried over from objektakte's `apps.classification.rules`
as specification, not code, docs/rules/M35-02.md).

`classify_document` evaluates a tenant's active `ObjektakteClassificationRule` rows against one
document, in priority order, and collects every match as a scored candidate (never only the
first hit, so the review case, if one is created, shows every rule that fired). The best
candidate's score decides the outcome:

- score >= tenant threshold: the document gets a **proposal only**
  (`document.source_meta["classification"]`, `stage="rules"`); `document.category_id` is never
  written here (rule 0.1.6, no autonomous classification; only a human decision in the review
  center, Stufe 3 part 3, applies a candidate).
- otherwise: an open `DocumentReviewCase` (`stage="rules"`) is created (or reused if one is
  already open for this document), carrying every candidate so a reviewer can pick one.

Pattern matching (docs/rules/M35-02.md):
- `filename_regex`: case-insensitive `re.search` against `document.filename`.
- `text_keyword`: case-insensitive `re.search` against `document.ocr_text` (a plain word is a
  valid regex, so this also covers a literal keyword).
- `sender_domain`: case-insensitive `re.search` against
  `document.source_meta.get("sender_email")` or `document.source_meta.get("sender_domain")`
  (whichever is set); no CRM module currently writes these keys for `mhvp.documents.Document`,
  so this pattern type only fires once an inbound channel (e.g. mail import) starts filling
  them.
- `drive_folder`: case-insensitive `re.search` against
  `document.source_meta.get("drive_folder_path")`.

A document with neither `ocr_text` nor a matching key in `source_meta` simply does not match
text/sender/folder rules; this is not an error.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import Document
from mhvp.objektakte.models import (
    ClassificationPatternType,
    DocumentReviewCase,
    ObjektakteClassificationRule,
    ReviewCaseStatus,
)
from mhvp.platform.models import TenantSettings

DEFAULT_AUTO_APPLY_THRESHOLD = 0.85


@dataclass
class RuleCandidate:
    rule_id: str
    rule_name: str
    pattern_type: str
    matched: str
    category_id: str | None
    document_type: str | None
    priority: int
    score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "pattern_type": self.pattern_type,
            "matched": self.matched,
            "category_id": self.category_id,
            "document_type": self.document_type,
            "priority": self.priority,
            "score": self.score,
        }


@dataclass
class RuleClassificationResult:
    candidates: list[RuleCandidate] = field(default_factory=list)
    threshold: float = DEFAULT_AUTO_APPLY_THRESHOLD
    applied_as_proposal: bool = False
    review_case_id: uuid.UUID | None = None

    @property
    def best(self) -> RuleCandidate | None:
        return self.candidates[0] if self.candidates else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.as_dict() for c in self.candidates],
            "threshold": self.threshold,
            "applied_as_proposal": self.applied_as_proposal,
            "review_case_id": str(self.review_case_id) if self.review_case_id else None,
        }


def _text_field(pattern_type: ClassificationPatternType, document: Document) -> str | None:
    if pattern_type is ClassificationPatternType.FILENAME_REGEX:
        return document.filename
    if pattern_type is ClassificationPatternType.TEXT_KEYWORD:
        return document.ocr_text
    if pattern_type is ClassificationPatternType.SENDER_DOMAIN:
        meta = document.source_meta or {}
        return meta.get("sender_email") or meta.get("sender_domain")
    meta = document.source_meta or {}
    return meta.get("drive_folder_path")


def _match(rule: ObjektakteClassificationRule, document: Document) -> str | None:
    value = _text_field(rule.pattern_type, document)
    if not value:
        return None
    try:
        compiled = re.compile(rule.pattern_value, re.IGNORECASE)
    except re.error:
        # An invalid pattern never matches instead of raising (a broken tenant rule must not
        # break every classification run); the rules settings form (Stufe 3 part 5) validates
        # on save.
        return None
    m = compiled.search(value)
    return m.group(0) if m else None


async def _active_rules(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[ObjektakteClassificationRule]:
    stmt = (
        select(ObjektakteClassificationRule)
        .where(
            ObjektakteClassificationRule.tenant_id == tenant_id,
            ObjektakteClassificationRule.active.is_(True),
        )
        .order_by(ObjektakteClassificationRule.priority.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _threshold(session: AsyncSession, tenant_id: uuid.UUID) -> float:
    stmt = select(TenantSettings.objektakte_classification).where(
        TenantSettings.tenant_id == tenant_id
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row and "auto_apply_threshold" in row:
        try:
            return float(row["auto_apply_threshold"])
        except (TypeError, ValueError):
            pass
    return DEFAULT_AUTO_APPLY_THRESHOLD


async def classify_document(
    session: AsyncSession, tenant_id: uuid.UUID, document: Document
) -> RuleClassificationResult:
    """Evaluate the rule stage for one document and persist the outcome on it (proposal in
    `source_meta`, or an open review case). Does not commit; the caller's transaction does."""
    rules = await _active_rules(session, tenant_id)
    threshold = await _threshold(session, tenant_id)
    candidates: list[RuleCandidate] = []
    for rule in rules:
        matched = _match(rule, document)
        if matched is None:
            continue
        candidates.append(
            RuleCandidate(
                rule_id=str(rule.id),
                rule_name=rule.name,
                pattern_type=rule.pattern_type.value,
                matched=matched,
                category_id=str(rule.target_category_id) if rule.target_category_id else None,
                document_type=rule.target_document_type,
                priority=rule.priority,
                score=float(rule.confidence),
            )
        )
    candidates.sort(key=lambda c: (-c.score, -c.priority))
    result = RuleClassificationResult(candidates=candidates, threshold=threshold)
    best = result.best
    if best is not None and best.score >= threshold:
        meta = dict(document.source_meta or {})
        meta["classification"] = {
            "stage": "rules",
            "status": "proposal",
            "category_id": best.category_id,
            "document_type": best.document_type,
            "confidence": best.score,
            "rule_id": best.rule_id,
            "candidates": [c.as_dict() for c in candidates],
        }
        document.source_meta = meta
        result.applied_as_proposal = True
        return result
    case = DocumentReviewCase(
        tenant_id=tenant_id,
        document_id=document.id,
        stage="rules",
        candidates={"candidates": [c.as_dict() for c in candidates]} if candidates else None,
        proposed_action=(
            {
                "action": "classify",
                "category_id": best.category_id,
                "document_type": best.document_type,
            }
            if best is not None
            else None
        ),
        priority=100,
        status=ReviewCaseStatus.OPEN,
    )
    session.add(case)
    await session.flush()
    meta = dict(document.source_meta or {})
    meta["classification"] = {
        "stage": "rules",
        "status": "review",
        "confidence": best.score if best is not None else None,
        "candidates": [c.as_dict() for c in candidates],
    }
    document.source_meta = meta
    result.review_case_id = case.id
    return result
