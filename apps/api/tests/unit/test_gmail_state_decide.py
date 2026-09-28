"""Rule M20-08, pure decision logic without a database: authoritative copies, folding of
history events (E19), attribution of own actions, the decision table E01 to E13, E16 to E18
and the aggregated sync state."""

import uuid
from dataclasses import replace

import pytest

from mhvp.communication.gmail import HistoryEvent
from mhvp.communication.gmail_state import (
    CopyView,
    authoritative,
    classify,
    classify_by,
    decide_group,
    fold,
    sync_state,
)

INFO, TIMO, POST, KOLLEGE = (uuid.uuid4() for _ in range(4))


def copy(
    mailbox: uuid.UUID | None,
    *,
    collective: bool = False,
    state: str = "inbox",
    expected: str | None = None,
    archive_history_id: int | None = None,
    echo: bool = False,
    gmail: bool = True,
    keep_open: str | None = None,
    status: str = "assigned",
    done_source: str | None = None,
    archive_status: str | None = None,
) -> CopyView:
    return CopyView(
        message_id=uuid.uuid4(),
        mailbox_id=mailbox,
        is_collective=collective,
        is_echo=echo,
        has_gmail_id=gmail,
        state=state,
        expected_state=expected,
        state_history_id=None,
        archive_history_id=archive_history_id,
        keep_open_label=keep_open,
        status=status,
        done_source=done_source,
        archive_status=archive_status,
    )


def decide(
    copies: list[CopyView], changed: CopyView, new_state: str, by: str = "user", **kw: object
):
    options = {"mode": "done", "done_on_trash": True, "reopen_on_unarchive": True} | kw
    return decide_group(copies, changed, new_state, by, **options)  # type: ignore[arg-type]


def test_authoritative_prefers_collective_copies_and_never_echoes() -> None:
    info, timo = copy(INFO, collective=True), copy(TIMO)
    assert [c.message_id for c in authoritative([timo, info])] == [info.message_id]
    kollege = copy(KOLLEGE)
    assert {c.message_id for c in authoritative([timo, kollege])} == {
        timo.message_id,
        kollege.message_id,
    }
    echo = copy(INFO, collective=True, echo=True)
    assert authoritative([echo, timo]) == [timo]
    assert authoritative([copy(None), copy(TIMO, gmail=False)]) == []


def test_fold_collapses_undo_snooze_and_trash_in_two_entries() -> None:
    e = lambda hid, kind, **kw: HistoryEvent(hid, "m", kind, **kw)  # noqa: E731
    folded = fold("inbox", [e(1, "inbox_removed"), e(2, "inbox_added")], frozenset())
    assert (folded.state, folded.coalesced) == ("inbox", 2)
    folded = fold("inbox", [e(1, "inbox_removed"), e(2, "trash_added")], frozenset())
    assert (folded.state, folded.coalesced) == ("trashed", 2)
    folded = fold("trashed", [e(3, "trash_removed"), e(3, "inbox_added")], frozenset())
    assert folded.state == "inbox"
    assert fold("trashed", [e(3, "trash_removed")], frozenset()).state == "archived"
    assert fold("inbox", [e(1, "spam_added")], frozenset()).state == "spam"
    assert fold("trashed", [e(1, "deleted")], frozenset()).state == "deleted"
    assert fold("inbox", [e(1, "added", label_ids=("TRASH",))], frozenset()).state == "trashed"
    labelled = fold(
        "inbox",
        [e(1, "label_added_other", added_labels=("Warten",)), e(2, "inbox_removed")],
        frozenset({"warten"}),
    )
    assert (labelled.state, labelled.keep_open_label) == ("archived", "Warten")
    assert (
        fold(
            "inbox", [e(1, "label_added_other", added_labels=("Other",))], frozenset({"warten"})
        ).keep_open_label
        is None
    )


def test_classify_by_recognises_own_actions() -> None:
    assert classify_by(copy(INFO, archive_history_id=50), "archived", 50) == "platform"
    assert classify_by(copy(INFO, archive_history_id=50), "archived", 51) == "user"
    assert classify_by(copy(INFO, expected="archived"), "archived", 99) == "platform"
    assert classify_by(copy(INFO, expected="archived"), "trashed", 99) == "user"
    assert classify_by(copy(INFO, expected="inbox", state="archived"), "inbox", 99) == "platform"
    assert classify_by(copy(INFO), "archived", 99) == "user"
    folded, by = classify(
        copy(INFO, expected="archived"),
        [HistoryEvent(7, "m", "inbox_removed")],
        keep_open_labels=frozenset(),
    )
    assert (folded.state, by) == ("archived", "platform")


def test_decision_table_personal_and_collective() -> None:
    info, timo = copy(INFO, collective=True), copy(TIMO)
    # E01: personal copy archived, collective still in the inbox.
    assert decide([info, timo], timo, "archived").effect == "ignored_personal"
    # E02: two collective mailboxes, one archived.
    post = copy(POST, collective=True)
    assert decide([info, post, timo], info, "archived").effect == "noted"
    # E03: last collective copy archived.
    archived_post = copy(POST, collective=True, state="archived")
    d = decide([info, archived_post, timo], info, "archived")
    assert (d.effect, d.group_action) == ("done", "complete")
    # E04, E05: no collective mailbox.
    kollege = copy(KOLLEGE)
    assert decide([timo, kollege], timo, "archived").effect == "noted"
    assert (
        decide([timo, copy(KOLLEGE, state="archived")], timo, "archived").group_action == "complete"
    )
    assert decide([timo], timo, "archived").group_action == "complete"
    # E13: work label blocks.
    labelled = replace(info, keep_open_label="Warten")
    assert decide([labelled, timo], labelled, "archived").effect == "ignored_keep_open"
    assert decide([info, replace(timo, keep_open_label="X")], info, "archived").group_action == (
        "complete"
    )
    # E16, E18: echo and own action.
    assert (
        decide([info, timo], copy(INFO, collective=True, echo=True), "archived").effect == "noted"
    )
    assert decide([info, timo], info, "archived", by="platform").effect == "ignored_own"
    # Spam never decides but does not block either.
    assert decide([info, timo], info, "spam").effect == "ignored_spam"
    spam_post = copy(POST, collective=True, state="spam")
    assert decide([info, spam_post, timo], info, "archived").group_action == "complete"


def test_decision_table_trash_delete_modes_and_reopen() -> None:
    info, timo = copy(INFO, collective=True), copy(TIMO)
    assert decide([info, timo], info, "trashed").group_action == "complete"
    assert decide([info, timo], info, "trashed", done_on_trash=False).effect == "noted"
    assert decide([info, timo], info, "deleted", done_on_trash=False).effect == "noted"
    assert decide([info, timo], info, "deleted").group_action == "complete"
    # Modes off and record_only never act.
    assert decide([info, timo], info, "archived", mode="record_only").group_action is None
    assert decide([info, timo], info, "archived", mode="off").group_action is None
    # Group already done: only a note.
    done_info = copy(INFO, collective=True, status="done", done_source="user")
    assert decide([done_info, copy(TIMO, status="done")], done_info, "archived").effect == "noted"
    # E10: restore of an authoritative copy of a done group reopens.
    d = decide([done_info, copy(TIMO, status="done", done_source="user")], done_info, "inbox")
    assert (d.effect, d.group_action) == ("reopened", "reopen")
    assert (
        decide([done_info, timo], done_info, "inbox", reopen_on_unarchive=False).effect == "noted"
    )
    assert decide([done_info, timo], done_info, "inbox", mode="record_only").effect == "noted"
    echo_done = copy(INFO, collective=True, status="done", done_source="echo")
    assert decide([echo_done], echo_done, "inbox").effect == "noted"
    # E11: restore of a personal copy.
    assert (
        decide([done_info, copy(TIMO, status="done")], copy(TIMO, status="done"), "inbox").effect
        == "ignored_personal"
    )


@pytest.mark.parametrize(
    ("views", "mode", "expected"),
    [
        ([copy(INFO, collective=True), copy(TIMO)], "off", "aus"),
        ([copy(None), copy(TIMO, gmail=False)], "done", "unbekannt"),
        ([copy(INFO, collective=True), copy(TIMO)], "done", "synchron"),
        ([copy(INFO, collective=True), copy(TIMO, state="archived")], "done", "abweichend"),
        (
            [copy(INFO, collective=True, archive_status="pending", status="done")],
            "done",
            "ausstehend",
        ),
        ([copy(INFO, collective=True, state="deleted"), copy(TIMO)], "done", "geloescht"),
        (
            [
                copy(INFO, collective=True, state="archived", status="done"),
                copy(TIMO, state="archived", status="done"),
            ],
            "done",
            "synchron",
        ),
        (
            [
                copy(INFO, collective=True, state="archived", status="done"),
                copy(TIMO, status="done"),
            ],
            "done",
            "abweichend",
        ),
    ],
)
def test_sync_state(views: list[CopyView], mode: str, expected: str) -> None:
    assert sync_state(views, mode) == expected
