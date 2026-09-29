"""Knowledge base context selection without a database (audit 29.09.2026,
``mhvp.ai.knowledge``): one row per group, count and character caps, stale hint; and the
category preference of the playbook match (``mhvp.communication.suggest.rank_playbooks``)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from mhvp.ai import knowledge
from mhvp.ai.models import AiKnowledgeKind, AiKnowledgeStatus
from mhvp.communication.suggest import (
    CATEGORY_BONUS,
    MIN_PLAYBOOK_SCORE,
    rank_playbooks,
    score_playbook,
)


def _entry(
    title: str,
    content: str = "Inhalt",
    *,
    group: uuid.UUID | None = None,
    version: int = 1,
    status: AiKnowledgeStatus = AiKnowledgeStatus.APPROVED,
    updated_at: datetime | None = None,
    superseded_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        group_id=group or uuid.uuid4(),
        version=version,
        kind=AiKnowledgeKind.FACT,
        title=title,
        content=content,
        status=status,
        superseded_at=superseded_at,
        deleted_at=None,
        created_at=updated_at or datetime.now(UTC),
        updated_at=updated_at or datetime.now(UTC),
    )


def test_dedupe_keeps_newest_version_per_group_in_ranked_order() -> None:
    group = uuid.uuid4()
    old = _entry("Regel v1", group=group, version=1)
    new = _entry("Regel v2", group=group, version=2)
    other = _entry("Andere Regel")
    text, used = knowledge.select_for_context([old, other, new])
    assert [u.title for u in used] == ["Regel v2", "Andere Regel"]
    assert "Regel v1" not in text
    assert text.startswith("- (fact) Regel v2: Inhalt")


def test_count_and_character_caps() -> None:
    rows = [_entry(f"Eintrag {i}", "x" * 100) for i in range(10)]
    _text, used = knowledge.select_for_context(rows, max_entries=3)
    assert len(used) == 3
    # Characters: each line is about 120 chars; a budget for two lines keeps two, a later
    # shorter entry may still fit (the order of the ranking decides, not the length).
    rows.append(_entry("Kurz", "k"))
    text, used = knowledge.select_for_context(rows, max_chars=260)
    assert [u.title for u in used] == ["Eintrag 0", "Eintrag 1", "Kurz"]
    assert len(text) <= 260


def test_long_entry_is_cut_visibly() -> None:
    row = _entry("Lang", "a" * 5000)
    text, used = knowledge.select_for_context([row], max_entry_chars=100)
    assert used == [row]
    assert text.endswith("[gekürzt]")
    assert len(text) < 200


def test_stale_only_for_live_approved_entries_older_than_the_window() -> None:
    now = datetime(2026, 9, 29, tzinfo=UTC)
    old = now - timedelta(days=knowledge.STALE_AFTER_DAYS + 1)
    fresh = now - timedelta(days=knowledge.STALE_AFTER_DAYS - 1)
    assert knowledge.is_stale(_entry("alt", updated_at=old), now)
    assert not knowledge.is_stale(_entry("neu", updated_at=fresh), now)
    assert not knowledge.is_stale(
        _entry("Entwurf", status=AiKnowledgeStatus.DRAFT, updated_at=old), now
    )
    assert not knowledge.is_stale(_entry("abgelöst", updated_at=old, superseded_at=now), now)


def _playbook(title: str, keywords: list[str], category: str | None = None) -> Any:
    return SimpleNamespace(id=uuid.uuid4(), title=title, keywords=keywords, category=category)


def test_rank_playbooks_prefers_the_mail_category_on_equal_keyword_hits() -> None:
    text = "Betreff: Wasserschaden im Bad\nDas Wasser tropft seit gestern aus der Decke."
    damage = _playbook("Wasserschaden melden", ["wasser", "decke", "keller"], "Schaden")
    insurance = _playbook("Versicherung Wasser", ["wasser", "decke", "keller"], "Versicherung")
    ranked = rank_playbooks(text, [insurance, damage], category="Schaden")
    assert [p.title for _s, p in ranked] == ["Wasserschaden melden", "Versicherung Wasser"]
    assert ranked[0][0] == min(1.0, score_playbook(text, damage.keywords) + CATEGORY_BONUS)
    # Without a category the original order of equal scores is kept.
    same = rank_playbooks(text, [insurance, damage])
    assert same[0][0] == same[1][0]


def test_rank_playbooks_never_lifts_a_playbook_without_keyword_hit() -> None:
    text = "Kündigung des Mietvertrags zum Monatsende"
    heating = _playbook("Heizung", ["heizung", "kalt"], "Kündigung")
    assert rank_playbooks(text, [heating], category="Kündigung") == []
    weak = _playbook("Vertrag", ["mietvertrag", "kaution", "übergabe", "schlüssel"], "Kündigung")
    ranked = rank_playbooks(text, [weak], category="Kündigung")
    assert ranked
    assert ranked[0][0] < MIN_PLAYBOOK_SCORE + CATEGORY_BONUS
