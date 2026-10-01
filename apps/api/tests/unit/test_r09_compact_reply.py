"""R09: the compact view passes the reply draft schema (tone, placeholders) of the suggestion."""

from types import SimpleNamespace
from typing import Any, cast

from mhvp.communication import compact
from mhvp.communication.suggest import draft_reply_payload


def _message(suggestion: dict[str, Any]) -> Any:
    return cast(Any, SimpleNamespace(suggestion=suggestion, subject="Heizung"))


def test_reply_block_carries_draft_schema() -> None:
    output = {"reply_draft": "{anrede}, zu {ticket} und {unbekannt}.", "reply_tone": "freundlich"}
    draft = draft_reply_payload(output, {"tone": "sachlich"})
    block = compact.reply_block(_message({**output, "draft_reply": draft}), "Guten Tag", 7)
    assert block["source"] == "suggestion"
    assert block["draft"]["tone"] == "freundlich"
    assert block["draft"]["style_tone"] == "sachlich"
    assert "{anrede}" in block["draft"]["placeholders"]
    assert block["draft"]["unknown_placeholders"] == ["{unbekannt}"]


def test_reply_block_without_draft_schema_is_unchanged() -> None:
    block = compact.reply_block(_message({"reply_draft": "Text"}), "Guten Tag", None)
    assert block == {"source": "suggestion", "text": "Text"}
