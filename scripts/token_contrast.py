"""WCAG 2.x contrast ratios for the MHVP token pairs, parsed from packages/ui/src/tokens.css.

Usage: python3 scripts/token_contrast.py [path/to/tokens.css] [--de]
Exit code 1 when a pair misses its target (4.5:1 text, 3:1 non text per WCAG 1.4.11).
"""
import re
import sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
css = open(args[0] if args else "packages/ui/src/tokens.css").read()
day_block = css[css.index(":root {") : css.index(':root[data-theme="evening"]')]
eve_block = css[css.index(':root[data-theme="evening"]') :]


def parse(block):
    out = {}
    for name, val in re.findall(r"--mhvp-color-([\w-]+):\s*([^;]+);", block):
        out[name] = val.strip()
    return out


day = parse(day_block)
eve = {**day, **parse(eve_block)}


def resolve(tokens, name):
    v = tokens[name]
    while v.startswith("var("):
        v = tokens[re.match(r"var\(--mhvp-color-([\w-]+)\)", v).group(1)]
    return v


def lum(hexv):
    hexv = hexv.lstrip("#")
    r, g, b = (int(hexv[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


PAIRS = [
    ("fg", "bg", 4.5, "Fließtext auf Seitengrund"),
    ("fg", "surface", 4.5, "Fließtext auf Karte"),
    ("fg", "surface-2", 4.5, "Fließtext auf Hover/Füllfläche"),
    ("fg", "raised", 4.5, "Text in Menüs und Dialogen"),
    ("fg", "field-bg", 4.5, "Eingabetext im Feld"),
    ("muted", "bg", 4.5, "Sekundärtext auf Seitengrund"),
    ("muted", "surface", 4.5, "Sekundärtext auf Karte"),
    ("muted", "surface-2", 4.5, "Sekundärtext auf Füllfläche"),
    ("subtle", "surface", 4.5, "Tabellenkopf, Labels auf Karte"),
    ("primary-fg", "primary", 4.5, "Primärbutton"),
    ("accent-fg", "accent", 4.5, "Text auf Akzentfläche"),
    ("fg", "accent-soft", 4.5, "Badge Akzent (badgeGold)"),
    ("success-fg", "success-bg", 4.5, "Badge Erfolg"),
    ("warning-fg", "warning-bg", 4.5, "Badge Warnung"),
    ("danger-fg", "danger-bg", 4.5, "Badge Fehler"),
    ("info-fg", "info-bg", 4.5, "Badge Info"),
    ("muted-fg", "muted-bg", 4.5, "Badge neutral"),
    ("progress-label-fg", "progress-label-bg", 4.5, "Namenslabel In Bearbeitung"),
    ("fg", "progress-bg", 4.5, "Text auf In Bearbeitung"),
    ("danger-fg", "surface", 4.5, "Fehlertext auf Karte"),
    ("success-fg", "surface", 4.5, "Erfolgstext auf Karte"),
    ("warning-fg", "surface", 4.5, "Warntext auf Karte"),
    ("rail-fg", "rail-bg", 4.5, "Navigation"),
    ("rail-muted", "rail-bg", 4.5, "Navigation Gruppenlabel"),
    ("rail-active-fg", "rail-active", 4.5, "Navigation aktiv"),
    ("field-line", "field-bg", 3.0, "Feldrahmen (Nicht-Text, 1.4.11)"),
    ("accent-strong", "surface", 3.0, "Fokusring auf Karte (Nicht-Text)"),
    ("accent-strong", "bg", 3.0, "Fokusring auf Seitengrund (Nicht-Text)"),
    ("accent-strong", "surface", 4.5, "Akzentlink auf Karte"),
    ("signal-critical", "surface", 3.0, "Ampel rot (Nicht-Text)"),
    ("signal-warning", "surface", 3.0, "Ampel orange (Nicht-Text)"),
    ("signal-ok", "surface", 3.0, "Ampel grün (Nicht-Text)"),
    ("signal-attention", "surface", 3.0, "Ampel gelb (Nicht-Text, nur mit Textlabel)"),
]

print("| Paar | Zweck | Tag | Abend | Soll |")
print("| --- | --- | --- | --- | --- |")
DE = "--de" in sys.argv
fail = False
for fg, bg, need, label in PAIRS:
    cells = []
    for t in (day, eve):
        try:
            r = ratio(resolve(t, fg), resolve(t, bg))
        except KeyError:
            cells.append("n/a")
            continue
        ok = r >= need
        fail |= not ok
        val = f"{r:.2f}".replace(".", ",") + " : 1" if DE else f"{r:.2f}:1"
        hexes = f"{resolve(t, fg)} auf {resolve(t, bg)}, " if DE else ""
        cells.append(f"{hexes}{val}{'' if ok else ' FAIL'}")
    soll = (str(need).replace(".", ",") + " : 1") if DE else f"{need}:1"
    print(f"| {fg} / {bg} | {label} | {cells[0]} | {cells[1]} | {soll} |")
sys.exit(1 if fail else 0)
