"""HTML mails with <style> in the body (operator report 30.09.2026)."""

from email.message import EmailMessage

from mhvp.communication import mail
from mhvp.communication.html import display_body, html_to_text, looks_like_markup, sanitize_html

NEWSLETTER = """<html><head><title>News</title><style>p{color:red}</style></head>
<body><style type="text/css">body { margin: 0; padding: 0; } .x td { font-size: 12px; }</style>
<!-- tracking comment -->
<table width="100%"><tr><td><table><tr><td><h1>Herbstausgabe</h1></td></tr>
<tr><td><p>Sehr geehrte Damen und Herren,</p><p>die   Heizperiode&nbsp;beginnt.</p></td></tr>
</table></td></tr></table><script>alert(1)</script></body></html>"""


def test_html_to_text_drops_style_script_comments_and_collapses_whitespace() -> None:
    text = html_to_text(NEWSLETTER)
    assert "margin" not in text
    assert "color" not in text
    assert "alert" not in text
    assert "tracking" not in text
    assert "News" not in text
    assert "Herbstausgabe" in text
    assert "die Heizperiode beginnt." in text
    assert "\n\n\n" not in text


def _html_only(html: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = "news@example.org"
    msg["Subject"] = "Newsletter"
    msg.set_content(html, subtype="html")
    return bytes(msg)


def test_parse_html_only_newsletter_has_clean_text() -> None:
    parsed = mail.parse(_html_only(NEWSLETTER))
    assert not parsed["body"].startswith("body {")
    assert "margin" not in parsed["body"]
    assert "Herbstausgabe" in parsed["body"]
    assert "margin" not in (sanitize_html(parsed["body_html"]) or "")


def test_parse_prefers_plain_part() -> None:
    msg = EmailMessage()
    msg["From"] = "a@example.org"
    msg.set_content("Klartext Teil")
    msg.add_alternative(NEWSLETTER, subtype="html")
    assert mail.parse(bytes(msg))["body"] == "Klartext Teil"


def test_parse_plain_part_with_css_uses_html() -> None:
    msg = EmailMessage()
    msg["From"] = "a@example.org"
    msg.set_content("body { margin: 0; padding: 0; }\nHerbstausgabe")
    msg.add_alternative(NEWSLETTER, subtype="html")
    body = mail.parse(bytes(msg))["body"]
    assert "margin" not in body
    assert "Herbstausgabe" in body


def test_display_body_repairs_stored_legacy_text() -> None:
    legacy = "body { margin: 0; padding: 0; } .x td { font-size: 12px; } Herbstausgabe"
    assert looks_like_markup(legacy)
    shown = display_body(legacy, sanitize_html(NEWSLETTER))
    assert shown is not None
    assert "margin" not in shown
    assert "Herbstausgabe" in shown
    no_html = display_body(legacy, None)
    assert no_html is not None
    assert "margin" not in no_html
    assert "Herbstausgabe" in no_html


def test_display_body_keeps_normal_text() -> None:
    text = "Guten Tag,\nbitte um Rückruf. Termin: 12.10.2026 {laut Absprache}"
    assert display_body(text, "<p>x</p>") == text
