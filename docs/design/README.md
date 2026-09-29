# Gestaltung der Web-CRM

Bausteine und Entscheidungen zur Oberfläche. Farb- und Abstandswerte stehen in
[tokens.md](tokens.md).

## Befehlspalette (Vorschlag 1, Betreiberentscheidung 27.09.2026)

`apps/web-crm/src/components/shell/CommandPalette.tsx` ersetzt die frühere Suche. Ein Eingabefeld,
geöffnet mit Strg+K, Cmd+K oder der Schaltfläche in der Kopfzeile, liefert in Gruppen: Zuletzt
geöffnet (localStorage je Benutzer), Aktionen (`palette-actions.ts`, je Aktion eine
Berechtigung), Navigation (alle Einträge der Seitenleiste, vom Layout übergeben) und Treffer
aus `GET /workspace/search`. Rollen `dialog`, `combobox`, `listbox` und `option`, Fokusfalle,
Escape schließt. Neue Aktionen werden in `palette-actions.ts` mit Berechtigung und i18n-Schlüssel
unter `Shell.action` eingetragen.

## Statuschip (Vorschlag 7)

`apps/web-crm/src/components/ui/StatusChip.tsx` zeigt einen Status als Symbol plus Klartext;
Farbe ist nur zweiter Bedeutungsträger. Die Zuordnung Status zu Text, Ton, Symbol und
Erklärung steht je Fachbereich in `apps/web-crm/src/lib/status-labels.ts` (Tickets, Mail,
Mahnläufe, Lastschriftläufe, Freigabestufen, Zählerzuordnungen). Eine Erklärung öffnet sich
als Popover (`role="tooltip"`, `aria-describedby`), zum Beispiel "Wartet auf Freigabe, G2
geschlossen: Freigabe durch zweite Person nötig". Übersetzte Beschriftungen aus den
Katalogen können per `label` übergeben werden. `StatusPill` bleibt für rein dekorative Fälle
bestehen; neue Statusanzeigen verwenden den Chip.

## Handy und Tablet (M31, Plan `docs/plans/M31-handy-tablet.md`)

Produktschutz und fachliche Umsetzung, keine Rechtspflicht. Entscheidung in ADR 0013.

### Drei Gerätestufen

| Stufe | Breite | Navigation | Inhalt |
| --- | --- | --- | --- |
| Handy | unter 640 px (unter `sm`) | Hamburger und Drawer (`MobileNav`, `NavDrawer`) | Karten statt Tabellen, gestapelte Aktionen, einspaltig |
| Tablet | 640 bis 1023 px (`sm` bis unter `lg`) | Hamburger und Drawer | volle Inhaltsbreite, Tabellen im Scrollwrapper, zwei Spalten |
| Desktop | ab 1024 px (`lg`) | Symbolrail 4,5 rem, ab 1280 px (`xl`) volle Rail 16 rem | wie bisher |

Die Rail Entscheidung steht in genau drei Dateien (`app/(app)/layout.tsx`, `shell/SideNav.tsx`,
`shell/MobileNav.tsx`). Modus `auto` rendert rein per CSS (`lg:w-[4.5rem] xl:w-64`, Beschriftungen
`lg:sr-only xl:not-sr-only`), ohne `matchMedia` und ohne Sprung nach der Hydration. Die manuellen
Modi `expanded` und `collapsed` liegen unter dem bestehenden Schlüssel `mhvp.nav.rail.collapsed`
(einziges lokal gespeichertes Shell Kennzeichen; alter Boolean wird toleriert) und werden als
`data-rail` auf `html` angekündigt. In der Symbolrail öffnet ein 44 px Knopf oben den Drawer mit
allen Gruppen (Fensterereignis `mhvp:open-nav`). Der Drawer benutzt dieselben Gruppenklappen und
dieselbe `PATCH /api/bff/auth/me/preferences` (`nav_expanded_groups`) wie die Rail (Betreiberregel:
Gruppen starten eingeklappt, geöffnete bleiben auf jedem Gerät offen), Fokus auf Schließen,
Tab bleibt im Panel, Fokus kehrt zum Auslöser zurück, Mandantenwechsel bei mehr als einem Mandanten.

Kopfzeile: eine Zeile von 56 px (64 px ab `sm`), Token `--mhvp-header-h`, Safe Area oben in der
Kopfzeile selbst. `main` schneidet mit `overflow-x-clip`, deshalb prüft Playwright Überlauf
elementweise (`getBoundingClientRect().right`).

### Zielgrößen nach Zeiger, nicht nach Breite

Bedienelemente sind 44 px (`min-h-11`) auf jedem Gerät und schrumpfen nur ab `sm` mit feinem
Zeiger (`sm:pointer-fine:min-h-10`, `sm:pointer-fine:h-9`), also mit Maus. Tailwind 4.3.3 bringt die
Varianten `pointer-coarse` und `pointer-fine` mit; eigene `@custom-variant` sind nicht erlaubt.
Kleinknöpfe (`ui.buttonSm`) wachsen mit `pointer-coarse:min-h-11`. Eingabefelder haben unter `sm`
16 px Schrift (`text-base sm:text-sm`) gegen den Fokus Zoom von iOS. Hover Zustände in
`packages/ui/src/base.css` gelten nur unter `@media (hover: hover)`, damit nach einem Tipp keine
Zeile markiert bleibt. Alles zentral in `apps/web-crm/src/lib/ui.ts`, festgeschrieben in
`ui.test.ts`.

### Primitive und ihre Pflicht

| Problem | Baustein | Regel |
| --- | --- | --- |
| Datentabelle | `ResponsiveList` (Karten unter `sm`, Tabelle ab `sm`), `ui.tableScroll`, `ui.tableCard` | Keine nackte `<table>` mehr; jede Tabelle hat einen Scrollwrapper oder eine Kartenfassung |
| Label und Wert | `KeyValueList` | Kein `grid-cols-2` ohne Breakpoint für Definitionslisten |
| Dialog, Formular, Galerie | `Sheet` (`sm`, `md`, `full`), `ConfirmSheet` mit `useConfirm()` | Kein `window.confirm`, kein eigener Portalcode |
| Feste Aktionsleiste | `BottomBar` (Viewport, `BOTTOM_BAR_SPACE` als Seitenabstand) und `ui.bottomBar` (klebend im Formular) | `pr-20` beziehungsweise `pr-[5.5rem]` halten die Ecke des KI Startknopfs frei, kein `h-screen` unter einer Leiste |
| Schrittleiste, Abschnitte | `ui.tabBar`, `ui.tab`, `ui.tabActive` | eine wischbare Zeile unter `sm`, umbrechend ab `sm` |
| Umschalter | `ui.segment`, `ui.segmentActive` | gleich breite Optionen |
| Symbolknopf | `ui.iconButton` | 44 px auf Touch, 36 px mit Maus |
| Medien Abfrage | `useMediaQuery` mit `PHONE` oder `TABLET` | nur für Verhalten, nie für Layout beim ersten Rendern |
| Netzstatus | `useOnline()` | Hinweis, kein Beweis der Erreichbarkeit |

Dateien der App (PDF, Anhänge) öffnen im selben Tab über den Dateiproxy, nie mit
`target="_blank"` und nie in einem `iframe` (Betreiberentscheidung M27-02 zu `X-Frame-Options`).
Keine Ablage von Protokolldaten, Fotos oder Unterschriften in `localStorage`, IndexedDB oder
einem Service Worker.

### z-Index Tabelle

| Ebene | z-Index |
| --- | --- |
| Tabellenkopf (sticky am oberen Rand des Scrollcontainers, unter der Kopfzeile nur mit `ui.tablePage`) | 1 |
| Kopfzeile | `z-30` |
| `BottomBar` | `z-30` |
| Popover, Menüs (Glocke, Benutzermenü, Statuschip Erklärung) | `z-40` (Chip `z-20` innerhalb der Seite) |
| KI Panel (Sperrzone `components/ai/*`) | `z-40` |
| Befehlspalette | `z-50` |
| `Sheet`, `ConfirmSheet` | `z-[90]` |
| Navigationsdrawer (Scrim, Panel) | `z-[99]`, `z-[100]` |
