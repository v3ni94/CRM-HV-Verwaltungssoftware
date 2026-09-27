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
