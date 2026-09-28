"""Antworten mit An/Cc (operator 27.09.2026): Reply-To-Kopfzeile beim Parsen und
"Antworten an alle" (``mhvp.communication.mail.build_reply_all``), deterministisch ohne
Datenbank."""

from email.message import EmailMessage

from mhvp.communication import mail


def _eml(*, sender: str, to: str, cc: str = "", reply_to: str = "") -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Mieterin <{sender}>"
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = "Frage"
    msg["Message-ID"] = "<m1@example.test>"
    msg["Date"] = "Wed, 23 Sep 2026 09:00:00 +0200"
    msg.set_content("Text")
    return bytes(msg)


def test_parse_captures_reply_to_header() -> None:
    parsed = mail.parse(
        _eml(
            sender="mieter@example.com",
            to="info@example.com",
            reply_to="Anders <anders@example.com>",
        )
    )
    assert parsed["reply_to"] == "anders@example.com"


def test_parse_without_reply_to_is_none() -> None:
    parsed = mail.parse(_eml(sender="mieter@example.com", to="info@example.com"))
    assert parsed["reply_to"] is None


def test_build_reply_all_uses_sender_without_reply_to() -> None:
    to, cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to=None,
        to_addresses=["info@example.com"],
        cc_addresses=[],
        own_addresses={"info@example.com"},
    )
    assert to == ["mieter@example.com"]
    assert cc == []


def test_build_reply_all_prefers_reply_to_over_sender() -> None:
    to, _cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to="anwalt@example.com",
        to_addresses=["info@example.com"],
        cc_addresses=[],
        own_addresses={"info@example.com"},
    )
    assert to == ["anwalt@example.com"]


def test_build_reply_all_removes_own_mailboxes_and_duplicates_of_to() -> None:
    to, cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to=None,
        to_addresses=["info@example.com", "post@example.com"],
        cc_addresses=["kollege@example.com", "mieter@example.com", "info@example.com"],
        own_addresses={"Info@Example.com", "post@example.com"},
    )
    assert to == ["mieter@example.com"]
    # info@ und post@ (eigene Postfächer) fallen weg, mieter@ ist Duplikat von To,
    # info@ als Cc-Duplikat ebenso; kollege@ bleibt als einziger echter Cc-Empfänger.
    assert cc == ["kollege@example.com"]


def test_build_reply_all_dedupes_cc_case_insensitively() -> None:
    to, cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to=None,
        to_addresses=[],
        cc_addresses=["a@example.com", "A@Example.com", "b@example.com"],
        own_addresses=set(),
    )
    assert to == ["mieter@example.com"]
    assert cc == ["a@example.com", "b@example.com"]


def test_build_reply_all_no_from_and_no_reply_to_yields_empty_to() -> None:
    to, cc = mail.build_reply_all(
        from_address=None,
        reply_to=None,
        to_addresses=["a@example.com"],
        cc_addresses=[],
        own_addresses=set(),
    )
    assert to == []
    assert cc == ["a@example.com"]


def test_build_reply_all_skips_null_and_blank_entries() -> None:
    """Hotfix 27.09.2026: NULL or blank array entries of stored rows never raise."""
    stored: list[str] = [None, "", "  ", " A@B.DE "]  # type: ignore[list-item]
    to, cc = mail.build_reply_all(
        from_address=" mieter@example.com ",
        reply_to="",
        to_addresses=stored,
        cc_addresses=[None, "mieter@example.com"],  # type: ignore[list-item]
        own_addresses={None, "info@example.com"},  # type: ignore[arg-type]
    )
    assert to == ["mieter@example.com"]
    assert cc == ["A@B.DE"]


# Review 1.40.2: To is never an own mailbox address ------------------------------------------

OWN = {"info@hv.example", "Post@HV.example"}


def test_own_reply_to_falls_back_to_foreign_sender() -> None:
    to, cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to="INFO@hv.example",
        to_addresses=["post@hv.example"],
        cc_addresses=["nachbar@example.com"],
        own_addresses=OWN,
    )
    assert to == ["mieter@example.com"]
    assert cc == ["nachbar@example.com"]


def test_mail_between_own_mailboxes_has_no_own_to() -> None:
    to, cc = mail.build_reply_all(
        from_address="info@hv.example",
        reply_to=None,
        to_addresses=["post@hv.example"],
        cc_addresses=["info@hv.example"],
        own_addresses=OWN,
    )
    assert to == []
    assert cc == []


def test_own_sender_replies_to_first_foreign_to_recipient() -> None:
    """Own sent mail (or a mail of an own mailbox) replied to: To is the first foreign
    original To recipient, the other foreign recipients stay in Cc."""
    to, cc = mail.build_reply_all(
        from_address="Post@hv.example",
        reply_to="info@hv.example",
        to_addresses=["post@hv.example", "mieter@example.com", "zweite@example.com"],
        cc_addresses=["anwalt@example.com", "MIETER@example.com"],
        own_addresses=OWN,
    )
    assert to == ["mieter@example.com"]
    assert cc == ["zweite@example.com", "anwalt@example.com"]


def test_own_sender_with_foreign_cc_only_leaves_to_empty() -> None:
    to, cc = mail.build_reply_all(
        from_address="info@hv.example",
        reply_to=None,
        to_addresses=["post@hv.example"],
        cc_addresses=["mieter@example.com"],
        own_addresses=OWN,
    )
    assert to == []
    assert cc == ["mieter@example.com"]


def test_foreign_reply_to_does_not_add_sender_to_cc() -> None:
    """RFC 5322 3.6.2: Reply-To names where the author wants replies; the sender is not added
    to Cc, unless he was an original recipient himself."""
    to, cc = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to="anwalt@example.com",
        to_addresses=["info@hv.example", "nachbar@example.com"],
        cc_addresses=[],
        own_addresses=OWN,
    )
    assert to == ["anwalt@example.com"]
    assert cc == ["nachbar@example.com"]
    _to, cc_self = mail.build_reply_all(
        from_address="mieter@example.com",
        reply_to="anwalt@example.com",
        to_addresses=["info@hv.example"],
        cc_addresses=["mieter@example.com"],
        own_addresses=OWN,
    )
    assert cc_self == ["mieter@example.com"]
