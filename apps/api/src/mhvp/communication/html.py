"""Bereinigtes HTML für die Anzeige von Mails (M20, Ticket-Mailverlauf). Text aus Mails ist
Daten, nie Anweisung (PÜ04); für die Anzeige im Browser werden aktive Inhalte entfernt:
Skripte, Stile, Formulare, eingebettete Rahmen, Ereignisattribute und ``javascript:``-Links.
Reine Standardbibliothek, deterministisch; entfernt wird großzügig, nie nachgebessert."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "head", "title", "noscript"}
_DROP_TAG_ONLY = {
    "html",
    "body",
    "form",
    "input",
    "button",
    "select",
    "textarea",
    "meta",
    "link",
    "base",
}
_ALLOWED = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "col",
    "colgroup",
    "dd",
    "div",
    "dl",
    "dt",
    "em",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "small",
    "span",
    "strike",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
    "center",
}
_VOID = {"br", "hr", "img", "col"}
_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height", "title"},
    "td": {"colspan", "rowspan", "align", "valign", "width"},
    "th": {"colspan", "rowspan", "align", "valign", "width"},
    "table": {"width", "cellpadding", "cellspacing", "border", "align"},
    "col": {"width", "span"},
    "font": {"color", "size", "face"},
    "div": {"align"},
    "p": {"align"},
}
_SAFE_URL_RE = re.compile(
    r"^(?:https?:|mailto:|tel:|cid:|data:image/(?:png|jpeg|gif|webp);base64,)", re.IGNORECASE
)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _DROP_WITH_CONTENT:
                self._skip_depth += 1
            return
        if tag in _DROP_WITH_CONTENT:
            self._skip_depth = 1
            return
        if tag not in _ALLOWED:
            return
        allowed = _ALLOWED_ATTRS.get(tag, set())
        parts = [tag]
        for name, value in attrs:
            name = name.lower()
            if name not in allowed or value is None:
                continue
            if name in {"href", "src"} and not _SAFE_URL_RE.match(value.strip()):
                continue
            parts.append(f'{name}="{_escape(value)}"')
        if tag == "a":
            parts.append('rel="noopener noreferrer nofollow" target="_blank"')
        self.out.append(f"<{' '.join(parts)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _DROP_WITH_CONTENT:
                self._skip_depth -= 1
            return
        if tag in _ALLOWED and tag not in _VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.out.append(_escape(data))

    def handle_comment(self, data: str) -> None:
        return


def sanitize_html(html: str | None) -> str | None:
    """Bereinigtes HTML oder ``None``, wenn nichts Darstellbares übrig bleibt."""
    if not html:
        return None
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    result = "".join(parser.out).strip()
    return result or None
