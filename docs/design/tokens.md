# Design Tokens der Oberfläche

Stand 27.09.2026, Betreiberentscheidung: Tagmodus ist Entwurf A "Klar und ruhig", Abendmodus ist
Entwurf B "Dunkel und präzise" (Version 1.37). Quelle im Code: `packages/ui/src/tokens.css`
(Werte je Modus), `packages/ui/src/theme.css` (Tailwind Zuordnung), `packages/ui/src/base.css`
(Basisklassen), Klassenvorgaben in `apps/*/src/lib/ui.ts`. Beide Web Apps binden dieselben
Dateien ein. Der Modus steht als `data-theme="day"` oder `data-theme="evening"` auf `html`,
gesetzt vom gemeinsamen Kern `packages/ui/src/theme-mode.ts` (Skript vor dem ersten Rendern,
Speicher, Umschalter `packages/ui/src/ThemeSwitch.tsx`), nie über eine `prefers-color-scheme`
Regel im CSS. Was Automatisch bedeutet, legt jede App fest: im CRM Abend von 19 bis 7 Uhr
(`apps/web-crm/src/lib/theme.ts`, Wahl je Benutzer auf dem Server), im Kundenportal die
Einstellung des Betriebssystems (`apps/web-portal/src/lib/theme.ts`, Wahl Hell, Dunkel oder
Automatisch nur im Browser gespeichert).

## Grundsätze

1. Zwei benannte Modi statt einer Invertierung. Die Mandantenmarke (V14) kann den Akzent zur
   Laufzeit überschreiben.
2. Farbe nur als Bedeutung: `success`, `warning`, `danger`, `info`, `muted`, `accent`, dazu die
   Ampel `signal-*`. Der Akzent (Orange #E6A83C) markiert Handlungsbedarf, Fokus und aktive
   Navigation, nie Fließtext; für Text und Fokusring gilt `accent-strong`.
3. Tag: weiche Karten auf warmem Grund, sehr weiche Schatten, Radien 10 bis 14 px. Abend: feine
   1px Linien, keine Schatten, Radius 6 px.
4. Komponenten verwenden ausschließlich semantische Klassen (`bg-surface`, `text-muted`,
   `border-field-line` usw.), keine Tailwind Palettenklassen (`bg-white`, `text-gray-*`) und keine
   Hexwerte. Ausnahme: Inhalte, die wie Papier wirken müssen, nutzen `paper` und `ink`.
5. Alle Text auf Hintergrund Paare erfüllen WCAG AA (Tabelle unten), Bedienelemente und Fokusring
   mindestens 3 : 1.
6. Einheitlicher Fokusring: 2px `accent-strong`, nur bei Tastaturfokus (`focus-visible`).
7. Alte Namen (`gold`, `gold-soft`, `gold-tint`, `anthracite-soft`) bleiben als Aliasse.

## Flächenrollen

| Rolle | Klasse | Einsatz | Tag | Abend |
| --- | --- | --- | --- | --- |
| Seitengrund | `bg-bg` | App Rahmen, Kopfzeile | #F6F5F2 | #0F1115 |
| Karte | `bg-surface` | `ui.card`, Tabellen, Buttons | #FFFFFF | #171A21 |
| Füllfläche | `bg-surface-2` | Zeilen Hover, verschachtelte Elemente, Code | #FAF9F7 | #1C2028 |
| Starke Füllung | `bg-surface-3` | gedrückt, Chat Blase, Skelett | #F0EFEB | #232833 |
| Schwebend | `bg-raised` | Menüs, Popover, Dialoge, Palette | #FFFFFF | #1C2028 |
| Eingabefeld | `bg-field-bg`, `border-field-line` | `ui.input` | #FFFFFF, #8F9095 | #12151B, #5B6373 |
| Kartenlinie | `border-card-line` | Karten und Tabellen | #EFEEE9 | #262B35 |
| Abdeckung | `bg-scrim` | Hintergrund modaler Dialoge | 40 % Anthrazit | 60 % Schwarz |
| Papier | `bg-paper`, `ink` | Unterschrift, QR Code, HTML Vorschau | #FFFFFF | #FFFFFF |

Diagramme: `chart-1` (neutrale Reihe), `chart-2` (Akzentreihe), `chart-grid`, `chart-axis`,
`chart-label`. Ampel: `signal-ok`, `signal-attention`, `signal-warning`, `signal-critical`, immer
zusammen mit einem Textlabel.

## Schrift

Variable UI Schrift Inter, geladen je App über `next/font/google` (selbst gehostet, kein externes
CSS, Variable `--font-inter`), Rückfall `system-ui`. Monospace: `ui-monospace` Stapel.

| Stufe | Klasse | Größe | Zeilenhöhe | Laufweite | Gewicht |
| --- | --- | --- | --- | --- | --- |
| Display | `mhvp-display` | 32px | 40px | -0,02em | 600 |
| H1 | `mhvp-title` | 24px | 32px | -0,015em | 600 |
| H2 | `mhvp-h2` | 18px | 24px | -0,01em | 600 |
| H3 | `mhvp-h3` | 16px | 24px | 0 | 600 |
| Fließtext | (body) | 14px | 22px | 0 | 400 |
| Klein | `mhvp-small` | 12px | 16px | 0 | 400 |
| Label | `mhvp-label` | 11px | 16px | 0,08em, Versalien | 500 |
| Mono | `mhvp-mono` | 13px | 20px | 0 | 400 |

Zahlen: `mhvp-num` und alle `mhvp-table` Zellen nutzen Tabellenziffern (`tabular-nums`).
Zahlenspalten erhalten die Zellklasse `num` (rechtsbündig). Tailwind: `text-display`, `text-h1`,
`text-h2`, `text-h3`, `text-body`, `text-small`, `text-mono`, `font-sans`, `font-mono`.

## Abstände (8 Punkt Raster)

| Token | Wert |
| --- | --- |
| `--mhvp-space-0-5` | 4px |
| `--mhvp-space-1` | 8px |
| `--mhvp-space-2` | 16px |
| `--mhvp-space-3` | 24px |
| `--mhvp-space-4` | 32px |
| `--mhvp-space-5` | 40px |
| `--mhvp-space-6` | 48px |
| `--mhvp-space-8` | 64px |

Tailwind Abstände (`p-4` = 16px, `gap-6` = 24px) liegen auf demselben Raster. Radien Tag: sm 6px,
md 10px, lg 12px (Karten), xl 16px. Radien Abend: sm 4px, md 6px, lg 6px, xl 8px.

## Farben und Kontrast

Kontrast nach WCAG 2.1 (relative Leuchtdichte), berechnet am 27.09.2026 mit
`python3 scripts/token_contrast.py --de` direkt aus `tokens.css` (Exitcode 1, sobald ein Paar sein
Ziel verfehlt). AA verlangt 4,5 : 1 für Text und 3 : 1 für Bedienelemente und Fokus (1.4.11).

| Paar | Zweck | Tag | Abend | Soll |
| --- | --- | --- | --- | --- |
| fg / bg | Fließtext auf Seitengrund | #1a1a1a auf #f6f5f2, 15,96 : 1 | #e8eaf0 auf #0f1115, 15,71 : 1 | 4,5 : 1 |
| fg / surface | Fließtext auf Karte | #1a1a1a auf #ffffff, 17,40 : 1 | #e8eaf0 auf #171a21, 14,47 : 1 | 4,5 : 1 |
| fg / surface-2 | Fließtext auf Hover/Füllfläche | #1a1a1a auf #faf9f7, 16,54 : 1 | #e8eaf0 auf #1c2028, 13,57 : 1 | 4,5 : 1 |
| fg / raised | Text in Menüs und Dialogen | #1a1a1a auf #ffffff, 17,40 : 1 | #e8eaf0 auf #1c2028, 13,57 : 1 | 4,5 : 1 |
| fg / field-bg | Eingabetext im Feld | #1a1a1a auf #ffffff, 17,40 : 1 | #e8eaf0 auf #12151b, 15,20 : 1 | 4,5 : 1 |
| muted / bg | Sekundärtext auf Seitengrund | #6b6c6f auf #f6f5f2, 4,82 : 1 | #9aa3b2 auf #0f1115, 7,43 : 1 | 4,5 : 1 |
| muted / surface | Sekundärtext auf Karte | #6b6c6f auf #ffffff, 5,25 : 1 | #9aa3b2 auf #171a21, 6,84 : 1 | 4,5 : 1 |
| muted / surface-2 | Sekundärtext auf Füllfläche | #6b6c6f auf #faf9f7, 4,99 : 1 | #9aa3b2 auf #1c2028, 6,42 : 1 | 4,5 : 1 |
| subtle / surface | Tabellenkopf, Labels auf Karte | #6b6c6f auf #ffffff, 5,25 : 1 | #9aa3b2 auf #171a21, 6,84 : 1 | 4,5 : 1 |
| primary-fg / primary | Primärbutton | #ffffff auf #1a1a1a, 17,40 : 1 | #0f1115 auf #e8eaf0, 15,71 : 1 | 4,5 : 1 |
| accent-fg / accent | Text auf Akzentfläche | #1a1a1a auf #e6a83c, 8,31 : 1 | #0f1115 auf #e6a83c, 9,03 : 1 | 4,5 : 1 |
| fg / accent-soft | Badge Akzent (badgeGold) | #1a1a1a auf #fff1d9, 15,61 : 1 | #e8eaf0 auf #1d2230, 13,19 : 1 | 4,5 : 1 |
| success-fg / success-bg | Badge Erfolg | #2f6b3a auf #edf6ee, 5,79 : 1 | #7bd69a auf #16301f, 8,08 : 1 | 4,5 : 1 |
| warning-fg / warning-bg | Badge Warnung | #9a5a00 auf #fde8d0, 4,60 : 1 | #f5c26b auf #3a2a10, 8,44 : 1 | 4,5 : 1 |
| danger-fg / danger-bg | Badge Fehler | #8b1d1d auf #fbe7e7, 7,72 : 1 | #f2aaaa auf #3a1717, 8,45 : 1 | 4,5 : 1 |
| info-fg / info-bg | Badge Info | #44474d auf #eef0f3, 8,16 : 1 | #9cc2ff auf #1e2a40, 7,93 : 1 | 4,5 : 1 |
| muted-fg / muted-bg | Badge neutral | #5b5c60 auf #f0efeb, 5,80 : 1 | #b4bcc9 auf #232833, 7,72 : 1 | 4,5 : 1 |
| progress-label-fg / progress-label-bg | Namenslabel In Bearbeitung | #6b4d00 auf #ffe8a8, 6,46 : 1 | #0f1115 auf #e6a83c, 9,03 : 1 | 4,5 : 1 |
| fg / progress-bg | Text auf In Bearbeitung | #1a1a1a auf #fff4d6, 15,88 : 1 | #e8eaf0 auf #1e1a10, 14,42 : 1 | 4,5 : 1 |
| danger-fg / surface | Fehlertext auf Karte | #8b1d1d auf #ffffff, 9,17 : 1 | #f2aaaa auf #171a21, 9,21 : 1 | 4,5 : 1 |
| success-fg / surface | Erfolgstext auf Karte | #2f6b3a auf #ffffff, 6,39 : 1 | #7bd69a auf #171a21, 9,89 : 1 | 4,5 : 1 |
| warning-fg / surface | Warntext auf Karte | #9a5a00 auf #ffffff, 5,47 : 1 | #f5c26b auf #171a21, 10,62 : 1 | 4,5 : 1 |
| rail-fg / rail-bg | Navigation | #55565a auf #ffffff, 7,33 : 1 | #9aa3b2 auf #0b0d11, 7,64 : 1 | 4,5 : 1 |
| rail-muted / rail-bg | Navigation Gruppenlabel | #6c6d70 auf #ffffff, 5,17 : 1 | #8a93a3 auf #0b0d11, 6,28 : 1 | 4,5 : 1 |
| rail-active-fg / rail-active | Navigation aktiv | #1a1a1a auf #fff1d9, 15,61 : 1 | #e6a83c auf #1d2230, 7,58 : 1 | 4,5 : 1 |
| field-line / field-bg | Feldrahmen (Nicht-Text, 1.4.11) | #8f9095 auf #ffffff, 3,19 : 1 | #5b6373 auf #12151b, 3,03 : 1 | 3,0 : 1 |
| accent-strong / surface | Fokusring auf Karte (Nicht-Text) | #935f08 auf #ffffff, 5,41 : 1 | #e6a83c auf #171a21, 8,32 : 1 | 3,0 : 1 |
| accent-strong / bg | Fokusring auf Seitengrund (Nicht-Text) | #935f08 auf #f6f5f2, 4,96 : 1 | #e6a83c auf #0f1115, 9,03 : 1 | 3,0 : 1 |
| accent-strong / surface | Akzentlink auf Karte | #935f08 auf #ffffff, 5,41 : 1 | #e6a83c auf #171a21, 8,32 : 1 | 4,5 : 1 |
| signal-critical / surface | Ampel rot (Nicht-Text) | #dc2626 auf #ffffff, 4,83 : 1 | #f87171 auf #171a21, 6,29 : 1 | 3,0 : 1 |
| signal-warning / surface | Ampel orange (Nicht-Text) | #ea6c0a auf #ffffff, 3,16 : 1 | #fb923c auf #171a21, 7,69 : 1 | 3,0 : 1 |
| signal-ok / surface | Ampel grün (Nicht-Text) | #16a36a auf #ffffff, 3,24 : 1 | #34d399 auf #171a21, 9,06 : 1 | 3,0 : 1 |
| signal-attention / surface | Ampel gelb (Nicht-Text, nur mit Textlabel) | #b88a00 auf #ffffff, 3,15 : 1 | #facc15 auf #171a21, 11,37 : 1 | 3,0 : 1 |

`subtle` ist für Labels und Hilfetexte gedacht, nicht für lange Absätze. Die Ampelfarben sind
Markierungen neben einem Textlabel und tragen die Bedeutung nie allein.

## Klassenvorgaben (`lib/ui.ts`)

`card`, `cardLift`, `cardLink`: Karte (`bg-surface`, `border-card-line`, `shadow-card`), Hover nur
über die Rahmenfarbe; die Markerklasse `mhvp-surface-card` lässt Tabellen darin flach. Eine
`mhvp-table` außerhalb einer Karte erscheint selbst als Karte. `input`: `bg-field-bg` mit
`border-field-line`. `primary`: neutrale Primäraktion (`bg-primary`), `button` und `secondary`
mit Akzent bei Hover. `popover` und `scrim` für schwebende Ebenen. Badges (`badge*`, `StatusChip`,
`StatusPill`) als runde Pillen in Halbfett auf den Statusflächen, neutral auf `muted-bg`. Alle
Bedienelemente: `focus-visible:ring-2 focus-visible:ring-focus`.

## Offen

- Freigabe der Unternehmensfarben (M1-08): danach `accent` und die Aliasse `gold*` mit den
  freigegebenen Werten belegen und die Kontrasttabelle neu berechnen.
- Die Farbe der Browserleiste im Kundenportal (`themeColor`) folgt der Einstellung des
  Betriebssystems, nicht einer manuellen Wahl Hell oder Dunkel.

## Handy und Tablet (M31)

- `--mhvp-header-h`: Höhe der Kopfzeile, 3,5 rem (56 px) unter `sm`, 4 rem (64 px) ab 640 px, in
  `packages/ui/src/tokens.css` unter `:root`. Klebende Elemente unter der Kopfzeile (Tabellenkopf
  `.mhvp-table thead th`, Abschnittsleisten `top-[var(--mhvp-header-h)]`, Sprungziele
  `scroll-mt-[calc(var(--mhvp-header-h)+3rem)]`) rechnen mit diesem Wert, nie mit einer Zahl.
  Der Tabellenkopf klebt nur, wenn die Tabelle mit der Seite scrollt; in einem Scrollwrapper
  scrollt er mit.
- Hover nur unter `@media (hover: hover)`: Zeilen Hover, Sticky Spalten Hover und `.mhvp-lift`
  in `base.css`. Fokus und aktive Zustände bleiben auf allen Geräten.
- Zeigervarianten statt Breitenvarianten für Zielgrößen: `pointer-coarse:` und `pointer-fine:`
  (Tailwind 4.3.3, eingebaut, gestapelt mit `sm:`). Beispiel `min-h-11 sm:pointer-fine:min-h-10`.
  Keine eigenen `@custom-variant`.
- `data-rail` auf `html` (`expanded` oder `collapsed`, fehlt bei `auto`): verschiebt die linke
  Kante der festen `BottomBar` (`.mhvp-bottom-bar`) ab `lg` auf die Railbreite.
