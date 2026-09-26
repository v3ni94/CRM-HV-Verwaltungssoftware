"""Ticketnummer im Betreff (TNR#<nummer>, docs/rules/M19-02-tnr.md) und bereinigtes HTML
für die Mailanzeige (M20): deterministische Helfer ohne Datenbank."""

from email.message import EmailMessage

from mhvp.communication import mail
from mhvp.communication.html import sanitize_html
from mhvp.tickets.tnr import extract_tnr, reply_subject, subject_with_tnr


def test_subject_with_tnr_is_added_exactly_once() -> None:
    assert subject_with_tnr("Wasserschaden Küche", 412) == "Wasserschaden Küche TNR#412"
    assert subject_with_tnr("Wasserschaden Küche TNR#412", 412) == "Wasserschaden Küche TNR#412"
    assert subject_with_tnr("AW: AW: Küche TNR#412 TNR#412", 412) == "AW: AW: Küche TNR#412"
    # Fremde Nummer (Weiterleitungsfehler) wird durch die Nummer dieses Tickets ersetzt.
    assert subject_with_tnr("Küche TNR#7", 412) == "Küche TNR#412"
    assert subject_with_tnr("", 3) == "TNR#3"
    assert subject_with_tnr(None, 3) == "TNR#3"


def test_reply_subject_keeps_one_prefix_and_one_tnr() -> None:
    assert reply_subject("Wasserschaden Küche", 412) == "AW: Wasserschaden Küche TNR#412"
    assert (
        reply_subject("AW: Wasserschaden Küche TNR#412", 412) == "AW: Wasserschaden Küche TNR#412"
    )
    assert reply_subject("Re: Frage", 5) == "Re: Frage TNR#5"


def test_extract_tnr() -> None:
    assert extract_tnr("AW: Wasserschaden Küche TNR#412") == 412
    assert extract_tnr("TNR#412: Rückfrage") == 412
    assert extract_tnr("Ticket 412") is None
    assert extract_tnr("TNR#") is None
    assert extract_tnr(None) is None


def test_sanitize_html_removes_active_content_and_keeps_markup() -> None:
    raw = (
        "<html><head><style>p{color:red}</style><title>x</title></head><body>"
        '<p onclick="alert(1)">Hallo <b>Welt</b></p>'
        "<script>alert(1)</script>"
        '<a href="javascript:alert(1)">böse</a> <a href="https://example.com">gut</a>'
        '<img src="https://example.com/a.png" alt="Bild" onerror="x()">'
        '<iframe src="https://evil"></iframe><form><input></form>'
        '<table><tr><td colspan="2">Zelle</td></tr></table></body></html>'
    )
    out = sanitize_html(raw) or ""
    for forbidden in ("<script", "alert", "<style", "iframe", "<form", "onclick", "onerror"):
        assert forbidden not in out
    assert "<p>Hallo <b>Welt</b></p>" in out
    assert '<a rel="noopener noreferrer nofollow" target="_blank">böse</a>' in out
    assert 'href="https://example.com"' in out
    assert '<img src="https://example.com/a.png" alt="Bild">' in out
    assert '<td colspan="2">Zelle</td>' in out
    assert sanitize_html("") is None
    assert sanitize_html("<script>x</script>") is None


def test_parse_exposes_cc_references_and_html() -> None:
    msg = EmailMessage()
    msg["From"] = "Erika <erika@example.com>"
    msg["To"] = "info@example.com"
    msg["Cc"] = "Hans <hans@example.com>, verwalter@example.com"
    msg["Subject"] = "Frage TNR#12"
    msg["Message-ID"] = "<m3@x>"
    msg["In-Reply-To"] = "<m2@x>"
    msg["References"] = "<m1@x>  <m2@x>"
    msg.set_content("Klartext")
    msg.add_alternative("<p>Klartext <b>fett</b></p><script>x</script>", subtype="html")
    parsed = mail.parse(bytes(msg))
    assert parsed["cc"] == ["hans@example.com", "verwalter@example.com"]
    assert parsed["to"] == ["info@example.com", "hans@example.com", "verwalter@example.com"]
    assert parsed["references"] == "<m1@x> <m2@x>"
    assert "<b>fett</b>" in parsed["body_html"]
    assert parsed["body"] == "Klartext"
