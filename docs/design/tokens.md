# Design Tokens der Oberfläche

Stand 27.09.2026, Betreiberentscheidung Designvorschlag 4 (ruhige Typografie und Farbsystem).
Quelle im Code: `packages/ui/src/tokens.css` (Werte), `packages/ui/src/theme.css` (Tailwind
Zuordnung), `packages/ui/src/base.css` (Basisklassen), Klassenvorgaben in `apps/*/src/lib/ui.ts`.
Beide Web Apps binden dieselben Dateien ein.

## Grundsätze

1. Neutrale Farbwerte, bis die Unternehmensfarben freigegeben sind (OPEN_QUESTIONS M1-08). Die
   Mandantenmarke (V14) überschreibt die Variablen zur Laufzeit.
2. Farbe nur als Bedeutung: `success`, `warning`, `danger`, `info`, `muted`, `accent`. Der Akzent
   markiert interaktive Zustände (Fokus, Hover, Marker), nie Fließtext.
3. Karten ohne Schatten, Trennung durch Haarlinien (1px, `border-hairline`). Schatten nur für
   schwebende Ebenen (Menüs, Dialoge, Hinweise).
4. Dunkelmodus eigenständig kalibriert, nicht invertiert; aktiv über `prefers-color-scheme` und
   `data-theme` auf `html`.
5. Alle Text auf Hintergrund Paare erfüllen WCAG AA (Tabelle unten).
6. Einheitlicher Fokusring: 2px Akzent, 2px Abstand, nur bei Tastaturfokus (`focus-visible`).
7. Alte Namen (`gold`, `gold-soft`, `gold-tint`, `anthracite-soft`) bleiben als Aliasse und zeigen
   bis zur Entscheidung M1-08 auf den neutralen Akzent.

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

Tailwind Abstände (`p-4` = 16px, `gap-6` = 24px) liegen auf demselben Raster. Radien: sm 6px,
md 8px, lg 12px (Karten), xl 16px.

## Farben und Kontrast

Kontrast nach WCAG 2.1 (relative Leuchtdichte), berechnet am 27.09.2026 mit dem Skript im
Verlauf dieser Änderung. AA verlangt 4,5 : 1 für Text, 3 : 1 für große Schrift und Bedienelemente.

### Hell

| Vordergrund | Hintergrund | Werte | Kontrast |
| --- | --- | --- | --- |
| fg | bg | #1f1f23 auf #ffffff | 16,43 : 1 |
| muted | bg | #5c5c66 auf #ffffff | 6,61 : 1 |
| subtle | bg | #75757f auf #ffffff | 4,56 : 1 |
| fg | surface | #1f1f23 auf #f6f6f7 | 15,21 : 1 |
| muted | surface | #5c5c66 auf #f6f6f7 | 6,12 : 1 |
| primary-fg | primary | #ffffff auf #1f1f23 | 16,43 : 1 |
| accent | bg | #2f5e95 auf #ffffff | 6,65 : 1 |
| accent-fg | accent | #ffffff auf #2f5e95 | 6,65 : 1 |
| success-fg | success-bg | #1a5a33 auf #e3f1e8 | 7,05 : 1 |
| warning-fg | warning-bg | #6f4a0a auf #fbeed3 | 6,87 : 1 |
| danger-fg | danger-bg | #8b1d1d auf #fbe7e7 | 7,72 : 1 |
| info-fg | info-bg | #1f4a75 auf #e4edf7 | 7,74 : 1 |
| rail-fg | rail-bg | #ececef auf #1d1d22 | 14,24 : 1 |
| rail-muted | rail-bg | #a3a3ab auf #1d1d22 | 6,70 : 1 |

### Dunkel

| Vordergrund | Hintergrund | Werte | Kontrast |
| --- | --- | --- | --- |
| fg | bg | #ececef auf #141417 | 15,59 : 1 |
| muted | bg | #b0b0b8 auf #141417 | 8,53 : 1 |
| subtle | bg | #8f8f98 auf #141417 | 5,73 : 1 |
| fg | surface | #ececef auf #1b1b20 | 14,55 : 1 |
| muted | surface | #b0b0b8 auf #1b1b20 | 7,96 : 1 |
| primary-fg | primary | #141417 auf #ececef | 15,59 : 1 |
| accent | bg | #8db4e6 auf #141417 | 8,58 : 1 |
| accent-fg | accent | #0f1a28 auf #8db4e6 | 8,18 : 1 |
| success-fg | success-bg | #9fd8b2 auf #16301f | 8,76 : 1 |
| warning-fg | warning-bg | #f0cf84 auf #3a2d10 | 8,94 : 1 |
| danger-fg | danger-bg | #f2aaaa auf #3a1717 | 8,45 : 1 |
| info-fg | info-bg | #a9c8ec auf #182a3f | 8,43 : 1 |
| rail-fg | rail-bg | #ececef auf #0f0f12 | 16,23 : 1 |
| rail-muted | rail-bg | #93939b auf #0f0f12 | 6,28 : 1 |

Alle Paare erfüllen AA, die meisten AAA. `subtle` ist für Labels und Hilfetexte gedacht, nicht für
lange Absätze.

## Klassenvorgaben (`lib/ui.ts`)

`card`, `cardLift`, `cardLink`: Haarlinie, kein Schatten, Hover nur über die Rahmenfarbe.
`primary`: neutrale Primäraktion (`bg-primary`), `button` und `secondary` mit Akzent bei Hover.
Alle Bedienelemente: `focus-visible:ring-2 focus-visible:ring-focus`. Neu: `h3`, `display`,
`small`, `num`, `mono`, `info`, `warning`, `badgeInfo`.

## Offen

- Freigabe der Unternehmensfarben (M1-08): danach `accent` und die Aliasse `gold*` mit den
  freigegebenen Werten belegen und die Kontrasttabelle neu berechnen.
- Inter im CRM: `apps/web-crm/src/app/layout.tsx` muss `Inter({ variable: "--font-inter" })`
  einbinden (Datei in Bearbeitung durch die Shell Aufgabe). Bis dahin greift `system-ui`.
