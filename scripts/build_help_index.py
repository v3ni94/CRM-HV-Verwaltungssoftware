#!/usr/bin/env python3
"""Build the page and handbook index for the assistant's "Wo finde ich ..." answers.

Sources (read only):
- ``apps/web-crm/src/lib/settings-index.ts``: settings pages and sections with href and
  permission (the same entries the settings search shows),
- ``MAIN_PAGES`` below: the main navigation of the CRM (``src/app/(app)/layout.tsx``),
- ``docs/handbuch/*.md``: one entry per ``## `` section with a short excerpt; the CRM page of
  the chapter comes from ``HANDBOOK_PAGES`` (the handbook itself is not rendered in the CRM).

Output: ``apps/api/src/mhvp/ai/help_index.json`` (committed; the API image has no ``docs/``).
``--check`` fails when the committed file is out of date (used by a pytest and ``make lint``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_INDEX = ROOT / "apps/web-crm/src/lib/settings-index.ts"
HANDBOOK = ROOT / "docs/handbuch"
TARGET = ROOT / "apps/api/src/mhvp/ai/help_index.json"
EXCERPT = 280

# Main navigation (layout.tsx), permission as there (None: always visible).
MAIN_PAGES: list[tuple[str, str, list[str], list[str] | None]] = [
    ("Start", "/start", ["dashboard", "übersicht", "startseite"], None),
    (
        "Objekte",
        "/objekte",
        ["objekt", "liegenschaft", "weg", "gebäude", "einheit"],
        ["properties:read"],
    ),
    ("Kontakte", "/kontakte", ["kontakt", "adressbuch", "eigentümer", "mieter", "person"], None),
    ("Kalender", "/kalender", ["termin", "kalender"], None),
    ("Fristen", "/fristen", ["frist", "wiedervorlage"], None),
    ("Mail", "/mail", ["mail", "postfach", "e-mail", "posteingang"], ["communication:read"]),
    ("Tickets", "/tickets", ["ticket", "vorgang", "anliegen", "schaden"], ["tickets:read"]),
    ("Vermietung", "/vermietung", ["vermietung", "leerstand", "mieterhöhung"], ["contracts:read"]),
    ("Verträge", "/vertraege", ["vertrag", "mietvertrag", "verträge"], ["contracts:read"]),
    ("Dokumente", "/dokumente", ["dokument", "datei", "upload"], ["documents:read"]),
    ("DMS", "/dms", ["dms", "ablage", "archiv"], ["documents:read"]),
    ("Buchhaltung", "/buchhaltung", ["buchhaltung", "buchung", "konto"], ["accounting:read"]),
    (
        "Abrechnung",
        "/abrechnung",
        ["abrechnung", "nebenkosten", "betriebskosten"],
        ["accounting:read"],
    ),
    ("Rechnungen", "/rechnungen", ["rechnung", "beleg", "eingangsrechnung"], ["accounting:read"]),
    ("Bank", "/bank", ["bank", "kontoauszug", "umsatz", "zahlung"], ["accounting:read"]),
    (
        "WEG",
        "/weg",
        ["weg", "eigentümerversammlung", "wirtschaftsplan", "hausgeld"],
        ["accounting:read"],
    ),
    ("Assistent", "/assistent", ["assistent", "ki", "chat"], None),
    ("Importe", "/importe", ["import", "datenübernahme"], None),
    ("Einstellungen", "/einstellungen", ["einstellungen", "konfiguration"], None),
]

# Handbook chapter -> CRM page it describes (None: no single page, excerpt only).
HANDBOOK_PAGES: dict[str, str | None] = {
    "abrechnung-miete.md": "/abrechnung",
    "anleitung-bankverbindung.md": "/kontakte",
    "assistent-chat.md": "/assistent",
    "anleitung-eigentuemerwechsel.md": "/objekte",
    "anleitung-mieterhoehung.md": "/vermietung/mieterhoehung",
    "anleitung-mieterwechsel.md": "/vertraege",
    "anleitung-objektordner.md": "/objektakte",
    "anleitung-stammdaten.md": "/objekte",
    "anleitung-verwalterwechsel.md": "/objekte",
    "auswertung-tickets.md": "/auswertung/tickets",
    "automatisierung.md": "/einstellungen",
    "banking.md": "/bank",
    "belegeingang.md": "/rechnungen",
    "buchhaltung.md": "/buchhaltung",
    "datenuebernahmen.md": "/importe",
    "dokumente-dms.md": "/dms",
    "einstellungen.md": "/einstellungen",
    "import-kontakte.md": "/importe",
    "import-objektdaten.md": "/importe",
    "import-zuordnung.md": "/importe",
    "kalender.md": "/kalender",
    "kontakte.md": "/kontakte",
    "mail.md": "/mail",
    "makler.md": "/makler",
    "objekte-einheiten.md": "/objekte",
    "start-auswertungen.md": "/start",
    "tickets.md": "/tickets",
    "vertraege.md": "/vertraege",
    "weg.md": "/weg",
}

ENTRY = re.compile(r"\{\s*id:\s*\"(?P<id>[^\"]+)\",(?P<body>.*?)\n  \},", re.S)


def _field(body: str, name: str) -> str | None:
    match = re.search(rf"\b{name}:\s*\"([^\"]*)\"", body)
    return match.group(1) if match else None


def _list(body: str, name: str) -> list[str] | None:
    match = re.search(rf"\b{name}:\s*(null|\[[^\]]*\])", body, re.S)
    if not match or match.group(1) == "null":
        return None
    return re.findall(r"\"([^\"]*)\"", match.group(1))


def settings_entries() -> list[dict[str, object]]:
    text = SETTINGS_INDEX.read_text(encoding="utf-8")
    out: list[dict[str, object]] = []
    for match in ENTRY.finditer(text):
        body = match.group("body")
        title, href = _field(body, "title"), _field(body, "href")
        if not title or not href:
            continue
        out.append(
            {
                "kind": "page",
                "title": title,
                "source": "Einstellungen",
                "href": href,
                "keywords": _list(body, "keywords") or [],
                "permission": _list(body, "permission"),
                "excerpt": "",
            }
        )
    return out


def _plain(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def handbook_entries() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for path in sorted(HANDBOOK.glob("*.md")):
        if path.name == "README.md":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        chapter = next((_plain(line[2:]) for line in lines if line.startswith("# ")), path.stem)
        href = HANDBOOK_PAGES.get(path.name)
        section: str | None = None
        body: list[str] = []

        def flush(
            heading: str | None,
            content: list[str],
            chapter: str = chapter,
            href: str | None = href,
            name: str = path.name,
        ) -> None:
            if heading is None:
                return
            excerpt = _plain(" ".join(content))[:EXCERPT]
            out.append(
                {
                    "kind": "handbook",
                    "title": heading,
                    "source": f"Handbuch: {chapter}",
                    "href": href,
                    "keywords": [],
                    "permission": None,
                    "excerpt": excerpt,
                    "file": f"docs/handbuch/{name}",
                }
            )

        for line in lines:
            if line.startswith("## "):
                flush(section, body)
                section, body = _plain(line[3:]), []
            elif section is not None:
                body.append(line)
        flush(section, body)
    return out


def build() -> str:
    entries: list[dict[str, object]] = [
        {
            "kind": "page",
            "title": title,
            "source": "Navigation",
            "href": href,
            "keywords": keywords,
            "permission": permission,
            "excerpt": "",
        }
        for title, href, keywords, permission in MAIN_PAGES
    ]
    entries += settings_entries()
    entries += handbook_entries()
    return json.dumps(entries, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    content = build()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            print(f"{TARGET.relative_to(ROOT)} is out of date: run scripts/build_help_index.py")
            return 1
        return 0
    TARGET.write_text(content, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
