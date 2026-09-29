# M31 Bedienung auf Handy und Tablet, Plan vom 28.09.2026

Ergebnis der strukturierten Analyse vom 28.09.2026 (sechs Bestandsaufnahmen, drei Entwürfe, drei Bewertungen). Betreiberdokument, Produktschutz und fachliche Umsetzung, keine Rechtspflicht. Gates G1 bis G5 bleiben geschlossen. Versionen setzt der Integrator beim Zusammenführen.

## Zusammenfassung

Umsetzungsplan M31 "Bedienung auf Handy und Tablet" (Produktschutz und Fachliche Umsetzung nach CLAUDE.md Abschnitt 5, keine Rechtspflicht). Rückgrat ist Entwurf 1 (Risk first, Gesamtwertung 99 von 120): Rail erst ab lg mit Symbolrail bis xl, Drawer bis lg, einzeilige Kopfzeile, Touch Ziele nach Zeigerart über die eingebauten Tailwind Varianten pointer-coarse und pointer-fine, 16 px Eingaben am Handy, Scrollwrapper Sweep und ResponsiveList, Schrittleiste mit Zählern im Übergabeeditor, keine lokale Speicherung, Gates G1 bis G5 geschlossen. Aus Entwurf 3 werden übernommen: echte Leseansicht HandoverSummary (Räume mit gruppierten Mängeln, Fotogitter, Unterschriften, PDF) ohne Editor Mount bei gesperrten Protokollen, Thumbnail Variante on the fly, Kopfzeilen Token --mhvp-header-h, Drawer mit serverseitigem Gruppenzustand, Playwright Helfer. Aus Entwurf 2: hint_codes als additives API Feld, Capture first Eintragsformular mit Status je Datei, clientseitige Verkleinerung vor dem Upload, Signaturkern mit normierten Strichen und Rückgängig, Unterschrift je Beteiligtem im Vollbild, Portal Menüeintrag Übergabe und Entfernen von target=_blank, useOnline Hinweis. Korrekturen aus den Urteilen: STEPS wird um defects ergänzt (heute 422), kein iframe PDF (X-Frame-Options DENY und frame-ancestors 'none' blockieren auch same-origin), Thumbnails ohne Browser Cache (no-store bleibt), image/heif nur mit Positivlisten Erweiterung und Test, keine eigenen coarse/fine Varianten, kein Autosave ohne Betreiberentscheidung (Rückfrage bei ungespeicherten Eingaben statt dessen), zutreffender Löschtext für Fotos, Tablet Test bei 820x1180 und 1024x768 statt Galaxy Tab S4. Fünf Arbeitspakete mit exklusivem Dateibesitz für parallele Worktrees: WP1 Shell und gemeinsame Bausteine, WP2 Übergabeeditor für Tablet und Handy, WP3 Datenseiten, WP4 Tests und E2E mit Mobilprojekten, WP5 PWA und Portalangleich (optional, teils an Betreiberentscheidungen gebunden). Integration über den Zweig feat/m31-handy-tablet; WP1 liefert am ersten Tag einen Fundament Commit (ui.ts Klassensätze, ResponsiveList, KeyValueList, Sheet, ConfirmSheet, BottomBar, useMediaQuery, useOnline, Token), dessen Schnittstellen in diesem Plan festgelegt sind, damit WP2 und WP3 sofort dagegen bauen können. Versionierung durch den Integrator beim Merge jedes Pakets (1.43.0 Shell, 1.44.0 Übergabe, 1.45.0 Datenseiten, 1.45.1 Testwächter, 1.46.0 PWA und Portal) in VERSION, CHANGELOG.md und apps/web-crm/src/lib/changelog.ts; Pakete liefern den Änderungstext im PR. Sperrzone apps/web-crm/src/components/ai/* und apps/api/src/mhvp/ai/* wird von keinem Paket berührt; Bodenleisten halten mit pr-20 die Ecke des KI Startknopfs frei.

## Grundsätze

- Drei Gerätestufen statt eines Umschaltpunkts: Handy unter 640 px (Karten, gestapelte Aktionen, Drawer), Tablet 640 bis 1023 px (Drawer, volle Inhaltsbreite, zwei Spalten), Desktop ab 1024 px (Symbolrail bis 1279 px per CSS, volle Rail ab 1280 px). Die Rail Entscheidung steht in genau drei Dateien ((app)/layout.tsx, SideNav.tsx, MobileNav.tsx) und wird nirgends dupliziert.
- Touch Maß nach Zeiger, nicht nach Breite: 44 px Ziele bleiben auf jedem Gerät mit grobem Zeiger (Tailwind 4.3.3 eingebaute Varianten pointer-coarse und pointer-fine, keine eigenen @custom-variant), nur Maus und Desktop schrumpfen auf 40 px; Eingabefelder 16 px unter 640 px gegen den iOS Fokus Zoom. Zentral in apps/web-crm/src/lib/ui.ts, per Test festgeschrieben.
- Nichts wird stumm abgeschnitten: main wechselt auf overflow-x-clip, jede Tabelle hat einen Scrollwrapper oder eine Kartenfassung, ein Quelltestscan verhindert neue nackte Tabellen, Playwright prüft Überlauf elementweise (getBoundingClientRect().right), weil der Clip die Dokumentbreite verfälscht.
- Ein Primitiv je Problemklasse, dann Seite für Seite: ResponsiveList, KeyValueList, Sheet und ConfirmSheet, BottomBar, StepNav Klassensätze (tabBar, tab, tabActive), tableScroll, tableCard, iconButton. Keine Seite erfindet eigene Klassenketten; gestylte Bausteine leben im CRM (Tailwind scannt nur App Quellen), packages/ui bleibt headless (CSS, theme-mode, signature-canvas).
- Der Server bleibt maßgeblich: Sperre nach Abschluss (409), Hinweise mit force, sanitize_image als einziger Weg in den Speicher (M30-04), PNG plus SHA-256 plus Zeitpunkt der Unterschrift und Einwilligungstext unverändert (M30-02), Zustellung nur als Entwurf mit Vier Augen Freigabe (M30-01, M20-01). Die Oberfläche rendert gespeicherte Daten, berechnet nichts nach und benutzt nie Wörter wie zugestellt, gelesen oder rechtsgültig (PÜ09, PÜ13).
- Datenschutz vor Komfort: keine localStorage, IndexedDB oder Service Worker Ablage von Protokolldaten, Fotos oder Unterschriften; Dateien und Object URLs nur im Speicher des Tabs mit Widerruf bei Unmount; Cache-Control private, no-store bleibt auf allen Dateipfaden einschließlich Thumbnails, bis der Betreiber anders entscheidet.
- Kein iframe, kein target=_blank für Protokolldateien: PDF und Anhänge öffnen als Same Tab Navigation über den Dateiproxy (Zurück führt zum Protokoll), Fotos in einer Galerie in der App. Eine Ausnahme von X-Frame-Options und frame-ancestors ist eine Sicherheitsentscheidung des Betreibers (M27-02), keine Implementierungsfrage.
- Editorlogik nur an benannten Stellen erweitern: Rückfrage bei ungespeicherten Eingaben, Erneut senden bei Netzfehler, Foto vor dem Speichern des Eintrags, Statuspunkte aus hint_codes. Feldweises Autosave, Schrittreihenfolge, Zähler aus Stammdaten und Änderungen nach vorhandener Unterschrift sind Betreiberentscheidungen und bleiben aus, bis sie getroffen sind.
- Exklusiver Dateibesitz je Arbeitspaket: nur messages/de.json und messages/en.json beider Apps, packages/ui/src/index.ts, docs/rules/README.md und docs/OPEN_QUESTIONS.md werden geteilt, ausschließlich additiv (neue Schlüssel, neue Zeilen am Ende des Namensraums, keine Umsortierung, keine Umbenennung). VERSION, CHANGELOG.md und changelog.ts pflegt allein der Integrator beim Merge.
- Jede Änderung hat einen Test, der auf Handybreite scheitert, bevor sie gebaut wird: vitest mit renderIntl für Struktur und Klassen, Playwright Projekte phone (390x844), tablet (820x1180) und tablet-landscape (1024x768) mit isMobile und hasTouch auf Chromium für Überlauf, Zielgrößen und den Übergabepfad; Safari und iPadOS werden nach einer versionierten Checkliste in docs/acceptance manuell abgenommen; nicht ausgeführte Tests werden ausdrücklich gemeldet.
- Sprache und Formate: Code, Kommentare, Commits und technische Doku Englisch; UI, Handbuch und Betreiberdokumente Deutsch ohne Gedankenstriche; TT.MM.JJJJ und 1.234,56 EUR; jeder neue Schlüssel in de.json und en.json beider Apps (strikte next-intl Tests).
- Kleine, nachvollziehbare Commits (Conventional Commits) auf Feature Zweigen je Paket, Integration in feat/m31-handy-tablet, Versionssprung zweite Stelle je Funktionspaket, dritte Stelle für Korrekturen; keine ungefragten Refactorings jenseits der benannten Dateien.

## Arbeitspakete

### WP1 Shell und gemeinsame Bausteine (Rail ab lg, Kopfzeile einzeilig, Touch Maß, Primitive, Tokens)

Ziel: Jede Seite des CRM wird auf Handy und Tablet auf einen Schlag benutzbar: Tablet Hochformat bekommt die volle Inhaltsbreite, Tablet Querformat eine Symbolrail, die Kopfzeile bleibt eine Zeile von 56 px, alle Steuerelemente sind auf Touch Geräten 44 px, Eingaben zoomen nicht, und die Bausteine ResponsiveList, KeyValueList, Sheet, ConfirmSheet, BottomBar, StepNav Klassen, useMediaQuery und useOnline stehen den Paketen WP2 und WP3 ab dem ersten Tag zur Verfügung.

Exklusiv bearbeitete Dateien:

- `apps/web-crm/src/app/(app)/layout.tsx`
- `apps/web-crm/src/app/layout.tsx`
- `apps/web-crm/src/components/shell/SideNav.tsx`
- `apps/web-crm/src/components/shell/SideNav.test.tsx`
- `apps/web-crm/src/components/shell/MobileNav.tsx`
- `apps/web-crm/src/components/shell/MobileNav.test.tsx`
- `apps/web-crm/src/components/shell/CommandPalette.tsx`
- `apps/web-crm/src/components/shell/CommandPalette.test.tsx`
- `apps/web-crm/src/components/shell/UserMenu.tsx`
- `apps/web-crm/src/components/shell/UserMenu.test.tsx`
- `apps/web-crm/src/components/shell/TenantSwitcher.tsx`
- `apps/web-crm/src/components/shell/icons.tsx`
- `apps/web-crm/src/components/workspace/NotificationBell.tsx`
- `apps/web-crm/src/components/workspace/NotificationBell.test.tsx`
- `apps/web-crm/src/components/workspace/ThemeToggle.tsx`
- `apps/web-crm/src/lib/ui.ts`
- `apps/web-crm/src/lib/ui.test.ts`
- `apps/web-crm/src/lib/useMediaQuery.ts`
- `apps/web-crm/src/lib/useMediaQuery.test.ts`
- `apps/web-crm/src/lib/useOnline.ts`
- `apps/web-crm/src/lib/useOnline.test.ts`
- `apps/web-crm/src/components/ui/ResponsiveList.tsx`
- `apps/web-crm/src/components/ui/ResponsiveList.test.tsx`
- `apps/web-crm/src/components/ui/KeyValueList.tsx`
- `apps/web-crm/src/components/ui/KeyValueList.test.tsx`
- `apps/web-crm/src/components/ui/Sheet.tsx`
- `apps/web-crm/src/components/ui/Sheet.test.tsx`
- `apps/web-crm/src/components/ui/ConfirmSheet.tsx`
- `apps/web-crm/src/components/ui/ConfirmSheet.test.tsx`
- `apps/web-crm/src/components/ui/BottomBar.tsx`
- `apps/web-crm/src/components/ui/BottomBar.test.tsx`
- `apps/web-crm/src/components/ui/PageHeader.tsx`
- `apps/web-crm/src/components/ui/StatusChip.tsx`
- `apps/web-crm/src/components/ui/StatusChip.test.tsx`
- `apps/web-crm/src/components/common/InlineField.tsx`
- `apps/web-crm/src/components/common/InlineField.test.tsx`
- `packages/ui/src/tokens.css`
- `packages/ui/src/theme.css`
- `packages/ui/src/base.css`
- `docs/design/README.md`
- `docs/design/tokens.md`
- `docs/adr/0013-responsive-primitives.md`

Geteilte Dateien (nur additiv):

- apps/web-crm/messages/de.json (Namensräume Shell.*, Ui.*, additiv)
- apps/web-crm/messages/en.json (additiv)

Abhängigkeiten:

- keine

Schritte:

1. Tag 1, Fundament Commit (wird zuerst in feat/m31-handy-tablet gemerged, Schnittstellen sind hiermit festgelegt): apps/web-crm/src/lib/ui.ts erhält tableScroll = "-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0", tableCard = card plus "overflow-x-auto p-0", cardsMobile = "flex flex-col gap-2 sm:hidden", tabBar = "-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] snap-x scroll-px-4 sm:mx-0 sm:flex-wrap sm:px-0", tab und tabActive (shrink-0 snap-start inline-flex min-h-11 items-center gap-1.5 rounded-full px-3.5 text-sm, aktiv bg-accent-soft font-semibold, Fokusring), bottomBar = "sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center gap-2 border-t border-border-soft bg-bg px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pr-20 sm:static sm:z-auto sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0" (pr-20 hält die Ecke des KI Startknopfs frei, dessen Datei nicht angefasst wird), iconButton = "inline-flex h-11 w-11 items-center justify-center rounded-md sm:pointer-fine:h-9 sm:pointer-fine:w-9", segment und segmentActive (min-h-11 flex-1 rounded-md border). Komponenten: ResponsiveList<T>({rows, keyOf, card, table, testId}) rendert ul.cardsMobile mit data-testid `${testId}-cards` und li.cardLink `${testId}-card`, darunter div tableCard hidden sm:block mit data-testid testId (Muster components/properties/PropertyList.tsx Zeile 29 bis 58, ohne Hooks, damit Server Seiten sie importieren dürfen). KeyValueList({items, num}) als dl grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 sm:grid-cols-[12rem_minmax(0,1fr)] mit min-w-0 break-words. Sheet({open, onClose, title, size: "sm"|"md"|"full", footer, initialFocusRef, children}): createPortal, bg-scrim, Body Scroll Lock, Escape, Schließen bei Routenwechsel, Safe Area, Fokusfalle und Erstfokus, role=dialog aria-modal aria-labelledby, unter md Bodenblatt fixed inset-x-0 bottom-0 max-h-[100dvh] rounded-t-xl mit scrollendem Körper und klebender Fußzeile, full = inset-0, ab md zentrierte Karte max-w-lg; z-[90]. ConfirmSheet plus Hook useConfirm(): confirm({title, text, confirmLabel, danger}) liefert Promise<boolean>. BottomBar({children}) als fixed inset-x-0 bottom-0 z-30 border-t bg-raised px-4 pt-2 pr-[5.5rem] lg:left-[4.5rem] xl:left-64 mit paddingBottom max(0.5rem, env(safe-area-inset-bottom)) und Export BOTTOM_BAR_SPACE = "pb-24"; unter der Bodenleiste kein h-screen. useMediaQuery(query) SSR sicher mit try/catch um matchMedia (Muster components/settings/SettingsSearch.tsx Zeile 24 bis 31), Konstanten PHONE und TABLET; useOnline() über navigator.onLine und online/offline Ereignisse. packages/ui/src/tokens.css: --mhvp-header-h: 3.5rem (ab sm 4rem) unter :root. Texte Ui.close, Ui.confirm, Ui.cancel, Ui.stepProgress ("Schritt {n} von {total}") in de.json und en.json.
2. Touch Maß und Feldschrift in ui.ts: input, button, primary, secondary, danger von "min-h-11 ... sm:min-h-10" auf "min-h-11 ... sm:pointer-fine:min-h-10" (gestapelte eingebaute Varianten, keine @custom-variant); input zusätzlich "text-base sm:text-sm"; buttonSm "min-h-9 pointer-coarse:min-h-11 pointer-coarse:px-3" (wirkt auf 314 Verwendungen). Kopfkommentar in ui.ts: Zielgrößen nach Zeiger, Breakpoints sm Tablet, lg Desktop.
3. packages/ui/src/base.css: tbody tr:hover (Zeile 162 bis 164), sticky-col hover (180 bis 182) und .mhvp-lift:hover (209 bis 211) in @media (hover: hover) hüllen; .mhvp-table thead th top: var(--mhvp-header-h); Kommentar Zeile 106 bis 108 ehrlich fassen (sticky Kopf wirkt nur ohne Scrollwrapper). Danach pnpm --filter @mhvp/web-portal test inklusive Accessibility.axe.test.tsx ausführen, weil beide Apps die CSS importieren.
4. Rail Entscheidung: (app)/layout.tsx Zeile 102 md:flex-row wird lg:flex-row; main wird "mx-auto w-full min-w-0 max-w-6xl flex-1 overflow-x-clip px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10"; Footer md:px-8 wird lg:px-8. SideNav.tsx Zeile 151 bis 155: alle md: des aside werden lg:, md:h-screen wird lg:h-dvh; railMode "auto"|"expanded"|"collapsed" unter RAIL_KEY mit tolerantem Parser (unbekannt oder alter Boolean true = collapsed, false = expanded, null = auto); auto rendert rein per CSS lg:w-[4.5rem] xl:w-64 mit Labels lg:sr-only xl:not-sr-only (kein matchMedia, kein Sprung nach Hydration); der Fußknopf schaltet auto, expanded, collapsed mit aria-pressed. Toten Kleinbildschirmpfad entfernen (Zeile 170, 191, 208), Gruppenknopf min-h-9, Fußknöpfe min-h-11. Rail Kopf bekommt einen 44 px Knopf lg:flex xl:hidden mit aria-label Shell.openNav, der den Drawer öffnet.
5. Drawer (MobileNav.tsx): Trigger und Portal Wrapper md:hidden werden lg:hidden, Trigger data-testid="nav-toggle"; Drawer als export NavDrawer({open, onClose, groups, initialExpandedGroups, tenants, currentTenant}) mit denselben Gruppenklappen und derselben PATCH /api/bff/auth/me/preferences nav_expanded_groups wie SideNav (Betreiberregel: Gruppen starten eingeklappt, geöffnete bleiben auf jedem Gerät offen), Icons aus shell/icons.tsx, Aktivprüfung mit useSearchParams wie SideNav.tsx Zeile 84 bis 86 (MobileNav in layout.tsx in Suspense mit Platzhalter h-11 w-11 hüllen), Fokus beim Öffnen auf den Schließen Knopf, Tab bleibt im Panel, Fokus kehrt zum Auslöser zurück; unter dem Drawerkopf ein TenantSwitcher (min-h-11 w-full text-base) nur bei tenants.length > 1.
6. Kopfzeile: layout.tsx Zeile 127 wird "sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border-soft bg-bg px-4 sm:h-16 sm:px-6 lg:px-8" mit style paddingTop env(safe-area-inset-top); das Body Padding Top in app/layout.tsx Zeile 40 entfällt (links, rechts bleiben). CommandPalette Trigger h-11 w-11 rund unter sm, ab sm wie heute (sm:min-w-56), Label hidden sm:flex, kbd hidden lg:inline; Dialog unter sm als Vollbild (p-0, Panel h-dvh flex-col, Eingabe oben angeheftet, Ergebnisliste min-h-0 flex-1, Optionszeilen min-h-11, Schließen Knopf min-h-11 sm:hidden mit Shell.close), Hervorhebung per onPointerMove statt nur Hover. NotificationBell: Knopf h-11 w-11 sm:h-10 sm:w-auto mit aria-label, Text hidden sm:inline, Popover fixed inset-x-4 top-[calc(var(--mhvp-header-h)+0.5rem)] max-h-[70vh] overflow-auto sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:w-80, Einträge min-h-11 sm:min-h-0. UserMenu Avatar h-11 w-11 sm:h-9 sm:w-9, Einträge min-h-11 sm:min-h-0, Außenklick per pointerdown. ThemeToggle Optionen min-h-11 sm:min-h-8. TenantSwitcher select min-h-11 text-base sm:min-h-10 sm:text-sm.
7. Kleine Steuerelemente: InlineField.tsx Zeile 235 bis 241 Stiftknopf auf ui.iconButton; PageHeader Breadcrumb Links inline-flex min-h-8 items-center; StatusChip Popover left-0 w-64 max-w-[calc(100vw-2rem)] mit Flip auf right-0, wenn getBoundingClientRect().right > innerWidth.
8. Dokumentation: docs/design/README.md Abschnitt "Handy und Tablet" (Stufen, Zielgrößen nach Zeiger, Primitive und ihre Pflicht: Tabellen nur über ResponsiveList, tableScroll oder tableCard, Dialoge über Sheet, feste Bodenelemente über BottomBar, keine target=_blank für In App Dateien, z-Index Tabelle: Kopfzeile z-30, BottomBar z-30, Popover z-40, Palette z-50, Sheet z-[90], Drawer z-[99]/z-[100], KI Panel z-40 in der Sperrzone); docs/design/tokens.md: --mhvp-header-h, Regel Hover nur unter @media (hover: hover), pointer Varianten; ADR 0013: gestylte Primitive im CRM, packages/ui headless, Portal Zwillinge in lib/ui.ts, Entscheidung gegen @custom-variant.
9. Ergebnisbericht mit ausgeführten Tests, Änderungstext für CHANGELOG im PR (Version setzt der Integrator: 1.43.0).

Tests:

- vitest apps/web-crm/src/lib/ui.test.ts: input, button, primary, secondary, danger enthalten min-h-11 und kein nacktes sm:min-h-10 (Regex (^|\s)sm:min-h-10), buttonSm enthält pointer-coarse:min-h-11, input enthält text-base und sm:text-sm, bottomBar enthält env(safe-area-inset-bottom) und pr-20, tab und tabActive enthalten min-h-11, tableScroll enthält overflow-x-auto.
- vitest ResponsiveList.test.tsx (Karten mit Testid, Tabellenwrapper hidden sm:block, leere rows ohne Fehler), KeyValueList.test.tsx, Sheet.test.tsx (Portal in body, Scroll Lock gesetzt und zurückgenommen, Escape und Scrim schließen, Fokusfalle, Fokus Rückkehr, Bodenblatt Klassen unter md per useMediaQuery Stub), ConfirmSheet.test.tsx (true bei Bestätigen, false bei Abbrechen), BottomBar.test.tsx (Safe Area Padding, pr-[5.5rem], lg:left-[4.5rem]), useMediaQuery.test.ts (ohne matchMedia false, mit Stub true), useOnline.test.ts.
- vitest SideNav.test.tsx: aside trägt lg:flex und kein md:flex, auto Modus lg:w-[4.5rem] xl:w-64, gespeichertes true ergibt collapsed, unbekannter Wert ergibt auto, PATCH nav_expanded_groups unverändert, Rail Kopfknopf lg:flex xl:hidden.
- vitest MobileNav.test.tsx: Trigger lg:hidden mit data-testid nav-toggle, Fokus nach Öffnen auf Schließen und nach Schließen auf dem Trigger, Tab bleibt im Panel, Aktivmarkierung /objekte?art=rental mit gemocktem useSearchParams, Gruppenklappen sendet PATCH nav_expanded_groups, TenantSwitcher bei zwei Mandanten sichtbar und bei einem nicht, bestehende Fälle Escape, Body Lock, z-[100] bleiben.
- vitest CommandPalette.test.tsx (Label hidden sm:flex, kbd hidden lg:inline, offener Dialog mit Schließen Knopf min-h-11 sm:hidden, Optionszeilen min-h-11), NotificationBell.test.tsx (aria-label, hidden sm:inline, fixed inset-x-4), UserMenu.test.tsx (pointerdown außerhalb schließt, Avatar h-11 w-11 sm:h-9), StatusChip.test.tsx (Flip Klasse bei simuliertem Überlauf), InlineField.test.tsx (Stiftknopf mit iconButton Klasse).
- pnpm --filter @mhvp/web-portal test nach jeder Änderung an packages/ui (Accessibility.axe.test.tsx in Tag und Abend, PortalNav.test.tsx, InstallHint.test.tsx).
- make lint (eslint --max-warnings=0, check_i18n, check_i18n_usage, check_client_imports: ResponsiveList und KeyValueList ohne Hooks) und make typecheck grün.

Abnahme:

- 390 px Handy (Hoch und Quer): Kopfzeile ist eine Zeile von 56 px, Hamburger, Suchsymbol, Glocke und Avatar sind je mindestens 44 x 44 px (boundingBox), kein Element ragt über den rechten Rand; Glocken Popover liegt vollständig im Viewport; Suche öffnet als Vollbild mit oben angehefteter Eingabe und Schließen Knopf; Drawer öffnet mit Fokus auf Schließen, zeigt Icons und Gruppen, markiert bei /objekte?art=rental nur Mietverwaltung, enthält bei zwei Mandanten den Mandantenwechsel; auf /start kein horizontaler Überlauf (elementweise geprüft); Anmeldefeld hat font-size 16 px und Höhe mindestens 44 px.
- 768 px Tablet Hochformat (1024er iPad gedreht): kein Rail Element sichtbar, Hamburger sichtbar, Inhalt nutzt die volle Breite abzüglich 48 px Rand; Knöpfe und Felder mindestens 44 px hoch (pointer coarse).
- 1024 px Tablet Querformat: Symbolrail 72 px sichtbar, kein Hamburger, der Knopf oben in der Rail öffnet den Drawer mit allen Gruppen; Rail Fußknöpfe liegen innerhalb von 100dvh; Inhalt mindestens 880 px breit; Knöpfe und Felder mindestens 44 px hoch.
- Beide Geräte: nach Antippen einer Tabellenzeile bleibt kein Hover Zustand stehen; Kleinknöpfe (buttonSm) sind 44 px hoch; StatusChip Erklärung am rechten Rand bleibt im Viewport; Tag und Abend Modus zeigen keine axe Verstöße in den Portal Tests.
- Desktop mit Maus 1280 px und mehr: Layout identisch zu heute (volle Rail, 40 px Felder), Palette Auslöser mit Strg+K Hinweis.

### WP2 Übergabeprotokoll Editor und Leseansicht für Tablet und Handy

Ziel: Ein Objektbetreuer erfasst eine Übergabe mit Tablet oder Handy Schritt für Schritt mit 44 px Zielen, richtiger Tastatur je Feld, Foto direkt beim Mangel oder Zähler (Kamera oder Galerie, verkleinert, mit Status je Datei), unterschreibt mit dem Beteiligten im Vollbild ohne Verzerrung beim Drehen, verliert keine Eingabe durch einen Schrittwechsel, und liest ein abgeschlossenes Protokoll in einer ruhigen Leseansicht mit Fotogalerie und PDF in der App. Fachregeln M30-01, M30-02, M30-04, M30-06 bleiben serverseitig maßgeblich; keine lokale Speicherung, keine Geldwege.

Exklusiv bearbeitete Dateien:

- `apps/web-crm/src/components/handover/HandoverEditor.tsx`
- `apps/web-crm/src/components/handover/HandoverEditor.test.tsx`
- `apps/web-crm/src/components/handover/HandoverSummary.tsx`
- `apps/web-crm/src/components/handover/HandoverSummary.test.tsx`
- `apps/web-crm/src/components/handover/HandoverList.tsx`
- `apps/web-crm/src/components/handover/HandoverList.test.tsx`
- `apps/web-crm/src/components/handover/PhotoPicker.tsx`
- `apps/web-crm/src/components/handover/PhotoPicker.test.tsx`
- `apps/web-crm/src/components/handover/PhotoStrip.tsx`
- `apps/web-crm/src/components/handover/PhotoStrip.test.tsx`
- `apps/web-crm/src/components/handover/PhotoGallery.tsx`
- `apps/web-crm/src/components/handover/PhotoGallery.test.tsx`
- `apps/web-crm/src/components/handover/SignaturePad.tsx`
- `apps/web-crm/src/components/handover/SignaturePad.test.tsx`
- `apps/web-crm/src/components/handover/SignatureSheet.tsx`
- `apps/web-crm/src/components/handover/SignatureSheet.test.tsx`
- `apps/web-crm/src/components/handover/steps.ts`
- `apps/web-crm/src/components/handover/steps.test.ts`
- `apps/web-crm/src/components/handover/useDirtyGuard.ts`
- `apps/web-crm/src/components/handover/useDirtyGuard.test.ts`
- `apps/web-crm/src/components/handover/HelperAccessSection.tsx`
- `apps/web-crm/src/components/handover/HelperAccessSection.test.tsx`
- `apps/web-crm/src/components/handover/HandoverCreate.tsx`
- `apps/web-crm/src/components/handover/PortalAccessBox.tsx`
- `apps/web-crm/src/components/handover/types.ts`
- `apps/web-crm/src/app/(app)/makler/uebergabe/page.tsx`
- `apps/web-crm/src/app/(app)/makler/uebergabe/neu/page.tsx`
- `apps/web-crm/src/app/(app)/makler/uebergabe/[id]/page.tsx`
- `apps/web-crm/src/app/api/handover-files/[...path]/route.ts`
- `apps/web-crm/src/app/api/handover-files/route.test.ts`
- `apps/web-crm/src/lib/image-downscale.ts`
- `apps/web-crm/src/lib/image-downscale.test.ts`
- `packages/ui/src/signature-canvas.ts`
- `packages/ui/src/signature-canvas.test.ts`
- `apps/api/src/mhvp/handover/models.py`
- `apps/api/src/mhvp/handover/routers.py`
- `apps/api/src/mhvp/handover/services.py`
- `apps/api/src/mhvp/handover/portal.py`
- `apps/api/src/mhvp/handover/images.py`
- `apps/api/src/mhvp/handover/README.md`
- `apps/api/src/mhvp/documents/text.py`
- `apps/api/tests/integration/test_m30_handover.py`
- `apps/api/tests/unit/test_m30_handover_images.py`
- `docs/rules/M30-01.md`
- `docs/rules/M30-07-fotos-thumbnails.md`
- `docs/plans/M30-uebergabeprotokoll.md`
- `docs/handbuch/anleitung-mieterwechsel.md`

Geteilte Dateien (nur additiv):

- apps/web-crm/messages/de.json (Namensraum Handover.*, additiv)
- apps/web-crm/messages/en.json (additiv)
- packages/ui/src/index.ts (Export signature-canvas, eine Zeile)
- packages/ui/package.json (exports Eintrag, additiv)
- docs/rules/README.md (Zeile für M30-07, additiv)
- apps/api/openapi.json und packages/api-client (nur per make openapi beim Integrieren regeneriert, nicht von Hand)

Abhängigkeiten:

- WP1 Fundament Commit (ui.ts Klassensätze, ResponsiveList, Sheet, ConfirmSheet, BottomBar, useOnline, useMediaQuery, Token --mhvp-header-h); die restlichen WP1 Schritte laufen parallel, WP2 rebased vor dem Merge

Schritte:

1. Server Abgleich zuerst (Regel 0.1.1, Ist Zustand gegen API prüfen): models.py STEPS um "defects" ergänzen (Reihenfolge der bestehenden Einträge unverändert; das Muster in ProtocolPatch leitet sich aus STEPS ab, current_step ist String(20), keine Migration); pytest Fall: PATCH current_step=defects antwortet 200. services.completion_hints liefert zusätzlich Codes (no_address, no_participants, no_meters, no_rooms, no_keys, no_signature, no_date, iban_invalid); _full_out und portal.py geben additiv hint_codes: list[str] neben dem unveränderten hints aus. Thumbnail Variante on the fly: GET /api/v1/handover/protocols/{id}/documents/{doc}/thumbnail (contracts:read, Dokument muss über services.documents_of mit dem Protokoll verknüpft sein, nur kind photo oder Bildanhang, sonst 404) liefert images.sanitize_image(data, mime, max_edge=320) als image/jpeg mit Cache-Control private, no-store (kein Browser Cache, Betreiberfrage offen), nichts wird gespeichert (S03 abgeleitete Ansicht); Portal Pendant unter /api/v1/portal/handover/{id}/documents/{doc}/thumbnail mit Grant Prüfung; documents_of ergänzt thumbnail_url je Bilddokument. GET /handover/protocols erhält den optionalen Filter handover_date (ISO Datum) für den Heute Chip. apps/api/src/mhvp/documents/text.py: "image/heif" in ALLOWED_MIME_TYPES aufnehmen (Sniffing kennt HEIF bereits), Unit Test mit HEIF Bytes. make openapi ausführen; README des Moduls fortschreiben.
2. Dateiproxy apps/web-crm/src/app/api/handover-files/[...path]/route.ts: Allowlist um ^handover/protocols/{ID}/documents/{ID}/thumbnail$ erweitern; route.test.ts prüft Allowlist und dass no-store auf allen Mustern bleibt.
3. Schrittleiste (HandoverEditor.tsx Zeile 441 bis 453): nav mit ui.tabBar, Knöpfe ui.tab beziehungsweise ui.tabActive, aria-current="step", Inhalt Beschriftung plus Zähler (SECTIONS Länge, attachments wie die bestehende Bedingung Zeile 1125, signatures Länge) und Statuspunkt aus p.hint_codes über steps.ts stepState (attention bei Code des Schritts, filled bei Inhalt, empty sonst; keine Textvergleiche); Effekt scrollIntoView({inline: "center", block: "nearest"}) in try/catch. Reihenfolge der 13 Schritte unverändert (Betreiberfrage). Schrittfußzeile mit Zurück und Weiter (ui.button und ui.primary mit ui.actionFull) in einem div ui.bottomBar unter dem Panel, Fortschrittstext Ui.stepProgress als sr-only; switchTab meldet einen fehlgeschlagenen current_step PATCH als unauffällige Info Zeile statt ihn zu verschlucken. Starttab bei locked ist summary; PATCH current_step nur bei !locked.
4. Leseansicht HandoverSummary({p, mode: "locked"|"overview", onGoTo}) rendert ausschließlich gespeicherte Daten: Kopfkarte (Nummer, Fassung, Statusbadge, Adresse, Einheit, Etage, Datum TT.MM.JJJJ, Zeit nur wenn hide_time_information false, Ort), Beteiligte (Rolle als Badge, Name oder Firma, Telefon als tel: und E-Mail als mailto: Link mit min-h-11), Zähler (Art, Nummer, Wert mit Einheit in ui.num, Ablesedatum), Räume mit Zustand als Badge und darunter die Mängel des Raums (Titel, Priorität, Status, Beschreibung, Fotogitter), nicht zugeordnete Mängel als eigener Block (wie pdf.py Zeile 384 bis 424), Schlüssel (Art, Anzahl, Status), Gegenstände, Bemerkungen (is_internal mit Badge Intern, im CRM sichtbar), Anhänge als Same Tab Links mit download Attribut, Unterschriften (Bild auf bg-paper max-h-28, Name, Rolle, "unterschrieben am" mit formatDateTime, Ort; keine Aussage zur Rechtswirkung), Fotoanzahl. Aktionen: PDF ansehen (Same Tab Link auf /api/handover-files/handover/protocols/{id}/pdf, kein target=_blank, kein iframe), Neue Fassung (bestehender Ablauf mit Grund), Zustellung vorbereiten (bestehender Ablauf, Beschriftung ohne Zustellbehauptung). Im Modus overview je Abschnitt ein Bearbeiten Knopf onGoTo(step) und die Hinweise oben mit Sprung zum Schritt. [id]/page.tsx rendert bei locked nur HandoverSummary mit Versionsliste und Aktionen; sonst den Editor, dessen Reiter summary HandoverSummary (overview) plus HelperAccessSection, Hinweise, Abschluss, Zustellung, Versionen zeigt. Karteninhalt der Teildatensätze am Handy (Reihenfolge fest): Raum = Name, Zustand, Anzahl Mängel und Fotos; Mangel = Titel, Raum, Priorität, Status, erstes Foto; Zähler = Art, Nummer, Wert mit Einheit, Ablesedatum; Schlüssel = Art, Anzahl, Status; Gegenstand = Bezeichnung, Zustand, Anzahl; Bemerkung = Kategorie, Text gekürzt, Frist.
5. Felder und Formulare: types.ts erhält INPUT_HINTS je Feldname (email type=email inputMode=email autoComplete=email; phone type=tel autoComplete=tel; postal_code inputMode=numeric autoComplete=postal-code; street, city, first_name, last_name, company mit autoComplete; deposit_iban und deposit_bic autoCapitalize=characters spellCheck=false autoComplete=off; meter_number, serial, key_number autoCapitalize=characters autoComplete=off; value, deposit_amount, count, quantity inputMode=decimal beziehungsweise numeric), Fields spreizt die Hinweise vor type, jedes Textfeld enterKeyHint="next", Textarea enterKeyHint="done". Feldraster Zeile 149 "grid gap-3 sm:grid-cols-2 lg:grid-cols-3", Zeile 205 sm:col-span-2 lg:col-span-3, Checkbox Label min-h-11 mit h-5 w-5. ProtocolForm und ItemForm Speichern in ui.bottomBar mit ui.actionFull; bei Fehlschlag (status 0 oder 5xx) bleibt der Wert im Formular, der Knopf heißt Erneut senden (Handover.retrySave), useOnline zeigt den Hinweis Handover.offlineNotice = "Keine Verbindung. Ungespeicherte Eingaben bleiben nur auf dieser Seite. Bitte die Seite nicht neu laden und nach Wiederherstellung der Verbindung erneut speichern." Kartenaktionen Zeile 849 bis 876: Bearbeiten links, Löschen rechts mit ml-auto und text-danger-fg, Löschen und Abschluss über ConfirmSheet statt window.confirm (bestehende Texte complete.confirm und complete.confirmForce bleiben; HandoverEditor.test.tsx Zeile 147 und 160 auf den ConfirmSheet umstellen). Kontaktsuche flex-col sm:flex-row, Hinzufügen ui.primary ui.actionFull, Unterschriftenliste sm:grid-cols-2, Zusammenfassung dl sm:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-2, Abschlussknöpfe ui.formActions, PDF Link ui.button ohne target=_blank, Kopfzeile Aktionen unter sm in einem Sheet Mehr (PDF, Termin, Stornieren, Archivieren). HelperAccessSection.tsx Zeile 148 Tabelle in ui.tableScroll, Aktionszelle whitespace-nowrap.
6. Rückfrage bei ungespeicherten Eingaben (einziger Logikzusatz neben Fotos): useDirtyGuard Kontext mit setDirty(id, boolean) und isDirty(); ProtocolForm und ItemForm melden onChange dirty true, nach erfolgreichem Save oder Abbrechen false; switchTab, Zurück, Weiter und Bearbeiten Sprünge fragen bei dirty per ConfirmSheet "Es gibt ungespeicherte Eingaben in diesem Abschnitt. Ohne Speichern fortfahren?" (Handover.unsavedConfirm, Knöpfe Hier bleiben und Verwerfen); beforeunload Listener solange dirty. Kein Autosave, keine localStorage Ablage (Betreiberfragen). Im Kommentar von HandoverEditor das Merge Muster für ein späteres Autosave festhalten: PATCH /protocols/{id} liefert nur _protocol_out, also setP(prev => ({...prev, ...data})), nie setP(data).
7. Fotos: PhotoPicker({files, onChange, disabled, single}) mit zwei sichtbaren ui.button Labels: Foto aufnehmen (input accept="image/*" capture="environment", einzeln) und Aus Galerie wählen (accept="image/jpeg,image/png,image/heic,image/heif" multiple ohne capture); Dateien nur im Komponentenzustand, Vorschau per URL.createObjectURL mit Widerruf bei Unmount, Entfernen je Datei 44 px. apps/web-crm/src/lib/image-downscale.ts: downscale(file) über createImageBitmap(file, {imageOrientation: "from-image"}) und Canvas toBlob("image/jpeg", 0.85) mit längster Kante 2000 px; Original zurück bei Dekodierfehler (HEIC ohne Decoder), bei Bild unter 2000 px und 1,5 MB oder ohne Canvas; Server Pipeline sanitize_image bleibt der einzige Weg in den Speicher (M30-04, Regelergänzung in docs/rules/M30-01.md: clientseitige Verkleinerung ist Transport, Prüfsumme gilt für das bereinigte Serverbild). Capture first: das Formular für einen neuen Eintrag in PHOTO_SECTIONS zeigt den PhotoPicker vor dem Speichern; bei Speichern zuerst POST des Eintrags, dann sequentieller Upload je Datei (FormData file, section, item_id) mit sichtbarer Statuszeile Wartet, Wird hochgeladen, Fertig, Fehlgeschlagen mit Erneut versuchen (nur diese Datei) und Später (Formular schließt, fehlgeschlagene Dateien bleiben aufgelistet bis zum Schließen); schlägt der POST fehl, bleiben Formular und Dateien stehen. Nach Uploads ein reload(); Photos Komponenten bekommen key={item.id}. PhotoStrip: Kacheln h-24 w-24 (Handy grid grid-cols-3 gap-2, ab sm flex-wrap) mit img src thumbnail_url, loading="lazy" decoding="async", Entfernen als 44 px Trefffläche mit 28 px Optik und ConfirmSheet mit zutreffendem Text Handover.photos.confirmRemove = "Foto aus dieser Fassung entfernen? Ist das Foto in keiner anderen Fassung verknüpft, wird die Datei endgültig gelöscht." (routers.py Zeile 588 bis 598). Tippen öffnet PhotoGallery (Sheet full, Bild object-contain aus /api/handover-files/documents/{id}/content, Wischen per Pointer Events und Pfeiltasten zwischen den Fotos desselben Eintrags, Zähler "3 von 12", Bildunterschrift aus itemTitle und created_at, Schließen 44 px). Anhänge Tab akzeptiert zusätzlich heic und heif, ohne capture, Same Tab Links.
8. Unterschrift: packages/ui/src/signature-canvas.ts headless (kein JSX, kein Tailwind): createSignatureStore mit Strichen als normierten Punktlisten (0..1 der CSS Box), useSignatureCanvas(canvasRef, {paper: "#ffffff", ink: "#1A1A1A", lineWidth: 2.2, maxRatio: 2}) mit Bitmap aus CSS Box mal devicePixelRatio (Deckel 2, damit das PNG unter 2 MB bleibt), ResizeObserver und orientationchange zeichnen alle Striche neu, Pointer Events mit setPointerCapture und touch-action none, undo(), clear(), isEmpty(), toDataURL() als data:image/png;base64 (Vertrag routers.py Zeile 43 und 617 bis 625 unverändert). CRM SignaturePad.tsx wird dünne Hülle (Reihenfolge: Beteiligter zuerst, Canvas h-56 sm:h-64, dann Name, Rolle, Ort in sm:grid-cols-3, Knöpfe Rückgängig, Leeren, Speichern in ui.formActions; Einwilligungstext unverändert). SignatureSheet: aus dem Reiter Unterschriften je Beteiligtem ohne Unterschrift ein Knopf "Unterschrift von {name}" plus "Weitere Person"; Sheet full mit Einwilligungstext, vorbelegtem Namen und Rolle (editierbar), Ort, Hinweis Handover.signature.handDevice = "Bitte das Gerät an {name} übergeben.", Canvas h-[45dvh] min-h-56 landscape:h-[60dvh], Fußzeile Rückgängig, Leeren, Unterschrift speichern; bei Erfolg schließen und Liste aktualisieren, bei Fehler (auch 409) Striche behalten und Meldung zeigen. Löschen einer Unterschrift vor Abschluss über ConfirmSheet, nach Abschluss nicht möglich (M30-01).
9. Liste makler/uebergabe/page.tsx: HandoverList (Client) mit ResponsiveList (Karte: Nummer und Fassung, Statusbadge, Adresse mit Einheit, Beteiligte, Datum; ganze Karte Link, testId handover), Filterformular als Suchfeld plus Filter Aufklapper (Muster components/tickets/TicketFilters.tsx Zeile 65, 183 bis 210, testid filters-toggle) und Chips Heute und Diese Woche als Query Parameter handover_date beziehungsweise Datumsbereich, Suchknopf ui.button ui.actionFull; Neu Knopf im PageHeader bleibt.
10. HandoverCreate.tsx Raster sm:grid-cols-2, Knöpfe ui.actionFull; PortalAccessBox Knöpfe 44 px über pointer-coarse (keine Logikänderung).
11. Dokumentation: docs/plans/M30-uebergabeprotokoll.md Stufe 5 "Bedienung am Tablet und Handy" mit Dateien, Tests, Entscheidungen; docs/rules/M30-07-fotos-thumbnails.md (Produktschutz: Thumbnail als abgeleitete Ansicht on the fly, kein Speicherobjekt, kein Browser Cache, keine Zugriffsprotokollierung bis zur Betreiberentscheidung, Zugriffsprüfung wie Original, Löschsemantik der Fotos); docs/rules/M30-01.md Ergänzung zur Verkleinerung; docs/handbuch/anleitung-mieterwechsel.md Abschnitt "Übergabe am Tablet oder Handy" (siehe handbook_changes); Änderungstext für CHANGELOG im PR (Version 1.44.0 setzt der Integrator).

Tests:

- pytest apps/api/tests/integration/test_m30_handover.py: PATCH current_step für alle 13 Client Schritte einschließlich defects antwortet 200; hint_codes parallel zu hints in CRM und Portal Full Output; Thumbnail Endpunkt 200 image/jpeg mit Cache-Control no-store und längster Kante 320, 404 für Dokument eines anderen Protokolls und für PDF, 403 ohne contracts:read, Mandantentrennung (fremdes Protokoll 404), Portal Variante nur mit Handover Grant; GET /handover/protocols mit handover_date; bestehende Abläufe (test_handover_flow, test_handover_portal_flow, test_helper_access_flow) unverändert grün. apps/api/tests/unit/test_m30_handover_images.py: HEIF Bytes passieren check_upload und werden als JPEG gespeichert. make openapi ohne Drift.
- vitest apps/web-crm/src/app/api/handover-files/route.test.ts: Thumbnail Muster erlaubt, no-store auf allen Mustern, unbekannte Pfade 404.
- vitest HandoverEditor.test.tsx (bestehende Fälle Raum anlegen, Hinweise und force, gesperrt, parseDecimal, Kaution, Portalzugang bleiben grün, ConfirmSheet statt window.confirm): Schrittknöpfe tragen min-h-11 und aria-current step; Weiter wechselt object auf participants und PATCHt current_step; Räume Reiter zeigt Zähler 1 nach Anlegen und Statuspunkt attention bei hint_codes no_rooms; email type=email, postal_code inputMode numeric, phone type=tel, deposit_iban autoCapitalize characters; Speichern Knopf liegt in einem Element mit Klasse sticky; fehlgeschlagener Save (status 0) behält den Wert und zeigt Erneut senden; Offline Hinweis bei navigator.onLine false; Rückfrage bei ungespeicherten Eingaben (Verwerfen wechselt, Hier bleiben bleibt und sendet kein PATCH); locked Fixture rendert HandoverSummary ohne Eingabefelder; Element.prototype.scrollIntoView gestubbt.
- vitest steps.test.ts: stepState für jeden hint_code liefert attention am richtigen Schritt, filled bei Inhalt, empty sonst.
- vitest HandoverSummary.test.tsx: Fixture mit zwei Beteiligten, Zähler 12.345,6 kWh, zwei Räumen mit je einem Mangel und einem nicht zugeordneten Mangel, Schlüssel, Unterschrift; prüft TT.MM.JJJJ, Dezimalkomma, tel: und mailto: Links, Gruppierung der Mängel unter dem Raum, eigenen Block für nicht zugeordnete, Badge Intern, Unterschriftsbild mit bg-paper, PDF Link ohne target=_blank und ohne die Wörter zugestellt oder rechtsgültig, Bearbeiten Knöpfe nur im Modus overview.
- vitest PhotoPicker.test.tsx (zwei Eingaben mit den angegebenen accept und capture Attributen, Dateien im Zustand, revokeObjectURL bei Unmount, Entfernen 44 px), image-downscale.test.ts (Rückfall auf Original ohne createImageBitmap oder bei Fehler; mit Stub wird 4000x3000 auf 2000x1500 skaliert und image/jpeg geliefert), HandoverEditor Capture first Fall (POST des Eintrags vor dem ersten Upload, FormData enthält section und item_id, fehlgeschlagene Datei markiert und nur diese erneut gesendet, Später schließt mit Liste), PhotoStrip.test.tsx (Kachel h-24, src enthält thumbnail, Entfernen nur nach ConfirmSheet mit dem Fallunterscheidungstext, Klick öffnet Galerie), PhotoGallery.test.tsx (Zähler, Vor und Zurück, Escape, Scroll Lock).
- vitest packages/ui/src/signature-canvas.test.ts (getContext Stub: Pointer down, move, up erzeugt einen Strich mit normierten Punkten, ResizeObserver Stub löst Neuzeichnen mit gleicher Strichzahl aus, undo entfernt den letzten Strich, clear leert, isEmpty, toDataURL beginnt mit data:image/png;base64, Bitmap Verhältnis maximal 2), SignaturePad.test.tsx (Beteiligter vor dem Canvas, Canvas h-56 und touch-none, Speichern ohne Strich zeigt signature.empty, POST Body mit image und participant_id), SignatureSheet.test.tsx (Knopf je Beteiligtem ohne Unterschrift, Name und Rolle vorbelegt, Einwilligungstext vorhanden, Erfolg schließt, 409 zeigt Meldung und behält Striche).
- vitest HandoverList.test.tsx (Karten unter sm mit testid handover-cards, Tabelle ab sm, Filter Aufklapper, Heute Chip setzt handover_date), HelperAccessSection.test.tsx (Wrapper tableScroll, bestehende Fälle grün).
- i18n: scripts/check_i18n.py, check_i18n_usage.py und i18n-consistency.test.ts für alle neuen Schlüssel Handover.stepPrev, stepNext, unsavedConfirm, retrySave, offlineNotice, photos.capture, photos.pick, photos.status.*, photos.retry, photos.later, photos.confirmRemove, gallery.*, signature.handDevice, signature.undo, summary.*, list.today, list.thisWeek, more.*; ohne Gedankenstriche.
- make lint, make typecheck (mypy strict, tsc), make test-api, pnpm --filter @mhvp/web-crm test, pnpm --filter @mhvp/ui test.

Abnahme:

- 390 px Handy (Hoch und Quer): Schrittleiste ist eine wischbare Zeile, jeder Chip mindestens 44 px hoch mit Zähler und Statuspunkt, der aktive Chip ist nach dem Wechsel sichtbar; Zurück und Weiter liegen unten über dem Home Indikator und links vom KI Startknopf, ohne Überlappung; im Schritt Mängel sendet der Wechsel PATCH current_step mit Antwort 200 (Netzwerk Tab); Feldraster einspaltig; Fokus auf ein Feld zoomt die Seite nicht; Telefon öffnet die Telefontastatur, Zählerstand die Dezimaltastatur, PLZ die Zifferntastatur; Speichern klebt unten sichtbar über der Tastatur (Prüfung auf echtem Gerät, visualViewport Verhalten notieren).
- Beide Geräte: neuer Mangel mit Foto ist ein Ablauf (Mangel hinzufügen, Raum wählen, Foto aufnehmen oder aus Galerie, Speichern) mit Statuszeile je Datei; hochgeladene Datei ist höchstens 2000 px lang (Serverbild) und der Upload eines 8 MB Fotos überträgt unter 1 MB (Netzwerk Tab); Kacheln sind 96 px und laden über den Thumbnail Pfad mit no-store; Tippen öffnet die Galerie mit Wischen und Zähler; Entfernen fragt mit dem Fallunterscheidungstext und trifft nicht versehentlich den Nachbarn (44 px Trefffläche).
- Beide Geräte: Unterschrift von {Beteiligter} öffnet das Vollbild mit Einwilligungstext, Namen und Rolle; Canvas mindestens 45 Prozent der Bildschirmhöhe; Drehen des Geräts während der Unterschrift erhält die Striche unverzerrt; Rückgängig entfernt den letzten Strich; gespeichertes PNG erscheint in der Liste mit Zeitpunkt; zweite Unterschrift desselben Beteiligten wird mit Meldung abgewiesen (409) und die Striche bleiben.
- Beide Geräte: Wechsel des Schritts mit ungespeicherter Eingabe zeigt die Rückfrage; Hier bleiben behält die Eingabe; Flugmodus während Speichern zeigt den Offline Hinweis, der Wert bleibt im Feld, Erneut senden speichert nach Wiederherstellung.
- Beide Geräte: abgeschlossenes Protokoll öffnet ohne Eingabefelder als Leseansicht mit Kopf, Beteiligten (Anrufen per tel:), Zählern, Räumen mit gruppierten Mängeln und Fotos, Schlüsseln, Unterschriften mit Zeitpunkt; PDF ansehen öffnet im selben Tab und Zurück führt zum Protokoll; interne Bemerkungen tragen die Kennzeichnung Intern; keine Wörter zugestellt, gelesen oder rechtsgültig.
- 768 px Hochformat: Feldraster zweispaltig, Liste als Tabelle mit Scrollwrapper, Schrittleiste umbrechend mit 44 px Chips; 1024 px Querformat: Feldraster dreispaltig neben der Symbolrail, Zusammenfassung zweispaltig, Unterschriftenliste zweispaltig; Liste zeigt bei 390 px Karten mit Nummer, Status, Adresse, Beteiligten und Datum, Heute Chip filtert serverseitig.
- Schutzregeln: Kaution bleibt Erfassung ohne Buchung; gesperrte Protokolle bieten keine Bearbeitung an; Zustellung vorbereiten erzeugt nur Entwürfe; kein Foto liegt nach Schließen des Tabs im Gerät (kein localStorage, kein Cache Eintrag im Browser Speicher).
- Nicht in CI prüfbar, manuell nach docs/acceptance Checkliste (WP4): iPadOS Safari Kamera und Galerie inklusive HEIC, Fokus Zoom, Drehung beim Unterschreiben, Same Tab PDF und Zurück.

### WP3 Datenseiten vor Ort: Tickets, Kontakte, Objekte und Einheiten, Kalender, Dokumente und der Tabellen Sweep

Ziel: Die Seiten, die ein Objektbetreuer unterwegs öffnet, sind am Handy Karten oder scrollende Tabellen ohne abgeschnittene Spalten, Definitionslisten stapeln sauber, der Kalender führt mit einem Tipp zur heutigen Übergabe, Kontakte lassen sich anrufen, Tickets nehmen Fotos aus der Kamera an, und keine der 21 nackten Tabellen wird mehr vom main Clip verschluckt.

Exklusiv bearbeitete Dateien:

- `apps/web-crm/src/app/(app)/tickets/page.tsx`
- `apps/web-crm/src/app/(app)/tickets/[ticketId]/page.tsx`
- `apps/web-crm/src/components/tickets/TicketsList.tsx`
- `apps/web-crm/src/components/tickets/TicketsList.test.tsx`
- `apps/web-crm/src/components/tickets/TicketSectionNav.tsx`
- `apps/web-crm/src/components/tickets/TicketSectionNav.test.tsx`
- `apps/web-crm/src/components/tickets/TicketForms.tsx`
- `apps/web-crm/src/components/tickets/TicketReplyPanel.tsx`
- `apps/web-crm/src/components/tickets/TicketProposals.tsx`
- `apps/web-crm/src/components/tickets/TicketWidth.test.tsx`
- `apps/web-crm/src/app/(app)/kontakte/page.tsx`
- `apps/web-crm/src/app/(app)/kontakte/[id]/page.tsx`
- `apps/web-crm/src/components/contacts/ContactMasterData.tsx`
- `apps/web-crm/src/components/contacts/ContactMasterData.test.tsx`
- `apps/web-crm/src/app/(app)/objekte/[propertyId]/page.tsx`
- `apps/web-crm/src/components/properties/UnitsTable.tsx`
- `apps/web-crm/src/components/properties/UnitsTable.test.tsx`
- `apps/web-crm/src/components/properties/PropertyPanels.tsx`
- `apps/web-crm/src/components/properties/UnitPanels.tsx`
- `apps/web-crm/src/components/properties/UnitDetails.tsx`
- `apps/web-crm/src/components/properties/UnitDetails.test.tsx`
- `apps/web-crm/src/app/(app)/vermietung/einheit/[unitId]/page.tsx`
- `apps/web-crm/src/app/(app)/kalender/page.tsx`
- `apps/web-crm/src/components/workspace/CalendarView.tsx`
- `apps/web-crm/src/components/workspace/CalendarView.test.tsx`
- `apps/web-crm/src/components/calendar/WeekView.tsx`
- `apps/web-crm/src/components/calendar/CreateEventDialog.tsx`
- `apps/web-crm/src/components/calendar/CreateEventDialog.test.tsx`
- `apps/web-crm/src/components/calendar/EventDetailDialog.tsx`
- `apps/web-crm/src/app/(app)/dokumente/page.tsx`
- `apps/web-crm/src/app/(app)/dokumente/[documentId]/page.tsx`
- `apps/web-crm/src/components/documents/DmsUpload.tsx`
- `apps/web-crm/src/components/documents/DmsUpload.test.tsx`
- `apps/web-crm/src/components/documents/DmsDocumentsPanel.tsx`
- `apps/web-crm/src/components/dms/DmsDocuments.tsx`
- `apps/web-crm/src/components/dms/DmsObjectTile.tsx`
- `apps/web-crm/src/components/mail/PostalOutbox.tsx`
- `apps/web-crm/src/components/mail/MailList.tsx`
- `apps/web-crm/src/components/mail/MailDetail.tsx`
- `apps/web-crm/src/components/workorders/WorkOrderProposals.tsx`
- `apps/web-crm/src/components/contracts/DepositPanel.tsx`
- `apps/web-crm/src/components/contracts/RentInvoicePanel.tsx`
- `apps/web-crm/src/components/contracts/ContractMandates.tsx`
- `apps/web-crm/src/components/contracts/ContractAllocationValues.tsx`
- `apps/web-crm/src/components/hoa/MeetingFormPanel.tsx`
- `apps/web-crm/src/components/hoa/AuditItemPicker.tsx`
- `apps/web-crm/src/components/metering/TransmissionsOverview.tsx`
- `apps/web-crm/src/components/metering/TransmissionWorkflow.tsx`
- `apps/web-crm/src/components/settings/CatalogAdmin.tsx`
- `apps/web-crm/src/components/settings/CustomFieldsAdmin.tsx`
- `apps/web-crm/src/components/settings/PortalFormSubmissions.tsx`
- `apps/web-crm/src/components/settings/DepositInterestRatesAdmin.tsx`
- `apps/web-crm/src/components/settings/TaxSettingsAdmin.tsx`
- `apps/web-crm/src/components/sla/ChannelsByLevelEditor.tsx`
- `apps/web-crm/src/components/imports/FullImport.tsx`
- `apps/web-crm/src/components/platform/OnboardingWizard.tsx`
- `apps/web-crm/src/components/platform/PricingAdmin.tsx`
- `apps/web-crm/src/components/dashboard/TicketAnalytics.tsx`
- `apps/web-crm/src/app/(app)/start/page.tsx`
- `docs/handbuch/kalender.md`
- `docs/handbuch/kontakte.md`

Geteilte Dateien (nur additiv):

- apps/web-crm/messages/de.json (Namensräume Calendar.*, Tickets.*, Contacts.*, Documents.*, Units.*, additiv)
- apps/web-crm/messages/en.json (additiv)

Abhängigkeiten:

- WP1 Fundament Commit (ui.tableScroll, tableCard, tabBar, tab, segment, iconButton, ResponsiveList, KeyValueList, Sheet, BottomBar, Token --mhvp-header-h)

Schritte:

1. Sweep A (mechanisch, ein Commit je Bereich): die 21 nackten Tabellen (PropertyPanels.tsx Zeile 114 und 172, UnitPanels.tsx Zeile 32, TicketProposals.tsx Zeile 216, WorkOrderProposals.tsx Zeile 89, PostalOutbox.tsx Zeile 211, DepositPanel, RentInvoicePanel, ContractMandates, ContractAllocationValues, MeetingFormPanel, AuditItemPicker, TransmissionsOverview, TransmissionWorkflow, CatalogAdmin, CustomFieldsAdmin, PortalFormSubmissions, DepositInterestRatesAdmin, TaxSettingsAdmin, ChannelsByLevelEditor, FullImport, OnboardingWizard, PricingAdmin) in <div className={ui.tableScroll}> (schlichte Tabellen) beziehungsweise ui.tableCard (mhvp-table) hüllen; keine Spalte und kein Inhalt ändert sich; DmsDocumentsPanel.tsx Zeile 127 bis 129 doppelten overflow-x-auto auf einen Wrapper reduzieren.
2. Sweep B Kartenfassungen mit ResponsiveList: UnitsTable.tsx (Karte: Nummer und Lage als Titel, Mieter, Eigentümer, Fläche in ui.num, Status; testId units), dokumente/page.tsx und DmsDocuments.tsx (Karte: Titel, Art, Datum; testId documents), kontakte/page.tsx behält seine bestehende Kartenliste (Testid contacts-cards) und tauscht nur die Tabellenhülle auf ui.tableCard.
3. Sweep C erzwungene Raster: einheit/[unitId]/page.tsx Zeile 124 und 135 und UnitDetails.tsx Zeile 115, 175, 185 auf KeyValueList; kontakte/[id]/page.tsx Zeile 69 grid-cols-3 wird grid-cols-1 sm:grid-cols-3; DmsObjectTile.tsx Zeile 25, CreateEventDialog.tsx Zeile 176, TicketAnalytics.tsx Zeile 448 und 452 grid-cols-2/3 werden grid-cols-1 sm:grid-cols-2/3; objekte/[propertyId]/page.tsx Zeile 209 md:grid-cols-2 wird lg:grid-cols-2; start/page.tsx Zeile 137 grid-cols-1 lg:grid-cols-3 wird grid-cols-1 md:grid-cols-2 xl:grid-cols-3 (Regel: drei und mehr Spalten erst ab xl, außer kleine KPI Karten).
4. Kalender: CalendarView.tsx Werkzeugleiste Zeile 205 bis 238 in zwei Zeilen unter sm (Heute Knopf neu mit Sprung zum aktuellen Monat und scroll-margin-top var(--mhvp-header-h) auf den ersten Eintrag von heute, Pfeile als ui.iconButton, Monatslabel min-w-0 flex-1 truncate; zweite Zeile Segment Monat und Woche über ui.segment, Eintrag als ml-auto); Monatszeilen Zeile 287 bis 333: li flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3, Datum tabular-nums ohne w-24, Label ohne w-28 mit truncate, Titel min-w-0 break-words [overflow-wrap:anywhere], Hinweise Wiederkehrend und Erinnerung als sichtbarer Kurztext statt title Attribut, Aktionen flex flex-wrap gap-2, bei item.kind === "handover" der Quelllink als ui.primary mit Beschriftung Calendar.openProtocol "Protokoll öffnen", Löschen unter sm in einem Sheet Mehr; heutige Einträge bg-surface-2 mit aria-current="date". WeekView.tsx Zeile 40 grid-cols-1 lg:grid-cols-7. CreateEventDialog und EventDetailDialog auf Sheet (size md) mit Absenden in der Fußzeile.
5. Kontakte: kontakte/[id]/page.tsx Zeile 217 bis 229 Reiterleiste auf ui.tabBar mit ui.tab und ui.tabActive und aria-current page (Server Seite rendert nur Klassen, keine Client Exports aufrufen); ContactMasterData und die Lese dl rendern Telefon als <a href="tel:"> und E-Mail als <a href="mailto:"> mit inline-flex min-h-11 items-center; Kontaktkopf mit zwei 44 px Aktionen Anrufen und E-Mail (Contacts.call, Contacts.mail), wenn Werte vorhanden. Einheit Seite: Bewohner (Mieter, Eigentümer) als Kartenliste mit Link zum Kontakt und denselben Aktionen.
6. Tickets: tickets/[ticketId]/page.tsx Blöcke in <section id=...> (bearbeiten, checkliste, mail, anhaenge, auftraege, vorschlaege, schaden, beirat, kommentare, verlauf, dokumente) mit scroll-mt-[calc(var(--mhvp-header-h)+3rem)]; TicketSectionNav (Client, ui.tabBar mit Ankerlinks, sticky top-[var(--mhvp-header-h)] z-20 bg-bg unter lg, IntersectionObserver in try/catch markiert den sichtbaren Abschnitt) unter dem PageHeader; TicketForms.tsx Zeile 203 bis 230 Labels als grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4; TicketsList.tsx Bulk Leiste Zeile 192 auf BottomBar (Testid bulk-bar bleibt), Toast Zeile 221 bottom-[calc(7rem+env(safe-area-inset-bottom))], Seitencontainer BOTTOM_BAR_SPACE; tickets/page.tsx Anlegen Link als ui.primary; TicketReplyPanel.tsx Zeile 337 und DmsUpload.tsx Zeile 95: accept="image/jpeg,image/png,image/heic,image/heif,application/pdf" plus zweites Label Kamera mit input accept="image/*" capture="environment" (einfaches Zwei Eingaben Muster ohne Verkleinerung; die Verkleinerung aus WP2 wird in einer Folgewelle geteilt, damit kein Cross Import zwischen den Worktrees entsteht); dokumente/[documentId]/page.tsx Zeile 89 und 94 und DmsDocumentsPanel.tsx Zeile 153 bis 166 Links ohne target=_blank als Same Tab Links mit download Attribut, wo es sich um Downloads handelt.
7. Mail: MailList.tsx Zeile 125 und MailDetail.tsx Zeile 116 sticky top-0 werden sticky top-[var(--mhvp-header-h)]; MailWorkspace Filterfelder min-w-[10rem] und [12rem] bleiben (unter 360 px).
8. Handbuch: docs/handbuch/kalender.md Abschnitt Heute und Protokoll öffnen am Handy; docs/handbuch/kontakte.md Abschnitt Anrufen und E-Mail vom Handy; Änderungstext für CHANGELOG im PR (Version 1.45.0 setzt der Integrator).

Tests:

- vitest UnitsTable.test.tsx, DmsDocuments Fall in bestehenden Tests, dokumente Seite: Karten mit Testid units-cards beziehungsweise documents-cards und Klasse sm:hidden, Tabellenwrapper hidden sm:block; MembersAdmin und OwnerPages Muster bleiben grün.
- vitest CalendarView.test.tsx: keine Klassen w-24 und w-28 in Monatszeilen, Wrap Klassen am Titel, Protokoll öffnen für kind handover, Heute wechselt den sichtbaren Monat, Wiederkehrend als sichtbarer Text; CreateEventDialog.test.tsx: role dialog im Sheet, Absenden in der Fußzeile, Raster grid-cols-1 sm:grid-cols-3; WeekView Klasse lg:grid-cols-7.
- vitest ContactMasterData.test.tsx: tel: und mailto: Links mit min-h-11, Aktionen Anrufen und E-Mail nur bei Werten; kontakte/[id] Reiter tragen min-h-11 und aria-current.
- vitest UnitDetails.test.tsx: KeyValueList mit Testid, keine Klasse grid-cols-2 ohne Breakpoint.
- vitest TicketSectionNav.test.tsx (Anker vorhanden, aktive Markierung bei gemocktem IntersectionObserver, kein Absturz ohne Observer), TicketsList.test.tsx (Bulk Leiste als BottomBar mit Testid bulk-bar, Toast Klasse mit safe-area), DmsUpload.test.tsx (zwei Eingaben mit den accept Listen, Kamera mit capture), TicketWidth.test.tsx unverändert grün.
- vitest apps/web-crm/src/lib/table-wrapper.test.ts (aus WP4) läuft nach Sweep A ohne Ausnahmen grün; no-fixed-width.test.ts (WP4 entfernt die Ausnahmen kalender und components/tickets) grün.
- i18n Schlüssel Calendar.today, Calendar.openProtocol, Calendar.more, Calendar.recurring, Calendar.reminder, Tickets.sections.*, Tickets.camera, Documents.camera, Documents.download, Contacts.call, Contacts.mail in de.json und en.json; make lint, make typecheck, pnpm --filter @mhvp/web-crm test.

Abnahme:

- 390 px Handy (Hoch und Quer): Einheitenliste eines Objekts, Dokumentenliste und DMS Liste zeigen Karten mit ganzflächigem Link; auf Objekt, Einheit, Vertrag, Postausgang, Vorschläge und Einstellungen sind alle Tabellenspalten per seitlichem Wischen erreichbar (elementweise kein Element rechts außerhalb des Scrollwrappers); Einheit und Kontakt Definitionslisten stapeln Label über Wert.
- 390 px: Kalender Werkzeugleiste in zwei Zeilen mit Heute, Monatszeilen brechen sauber um, die heutige Übergabe zeigt Protokoll öffnen als Primärknopf (44 px) und führt zum Protokoll; Termin anlegen öffnet als Bodenblatt mit Absenden über der Tastatur.
- 390 px: Kontaktreiter sind eine wischbare Zeile, alle zehn Reiter erreichbar; Anrufen und E-Mail Knöpfe 44 px, tel: Link öffnet die Telefon App (Gerät); Ticket Detail hat eine klebende Abschnittsnavigation unter der Kopfzeile, Kommentare sind mit zwei Tipps erreichbar; Bulk Leiste liegt über dem Home Indikator und nicht unter dem KI Startknopf; Ticket Antwort und DMS Upload bieten Kamera und Dateiwahl inklusive HEIC.
- 768 px Hochformat: Tabellen ab sm sichtbar mit Scrollwrapper, Wochenansicht als Tagesliste (sieben Spalten erst ab 1024 px), Start Seite zweispaltig; 1024 px Querformat: Wochenansicht siebenspaltig, Start Seite zweispaltig (drei Spalten erst ab 1280 px), Objektseite Kontakte zweispaltig.
- Desktop 1280 px und mehr: keine sichtbare Änderung außer Heute Knopf, Abschnittsnavigation der Tickets und den Kartenlisten unter sm (unsichtbar am Desktop).

### WP4 Tests und E2E mit Handy und Tablet Viewports, Quelltestwächter, Geräte Checkliste

Ziel: Handy und Tablet Layouts sind in CI abgesichert: drei Playwright Projekte (phone 390x844, tablet 820x1180, tablet-landscape 1024x768, Chromium, isMobile, hasTouch) prüfen Überlauf elementweise, Zielgrößen, Kopfzeilenhöhe, die Shell und den vollständigen Übergabepfad; Quelltestscans verhindern neue nackte Tabellen und feste Breiten in beiden Apps; die manuelle Safari und iPadOS Abnahme hat eine versionierte Checkliste; die CI Budgets sind mit Zahlen belegt.

Exklusiv bearbeitete Dateien:

- `apps/web-crm/playwright.config.ts`
- `apps/web-portal/playwright.config.ts`
- `apps/web-crm/e2e/mobile-layout.ts`
- `apps/web-crm/e2e/shell.mobile.spec.ts`
- `apps/web-crm/e2e/handover.mobile.backend.spec.ts`
- `apps/web-crm/e2e/pages.mobile.backend.spec.ts`
- `apps/web-crm/e2e/fixtures/photo.jpg`
- `apps/web-portal/e2e/mobile-layout.ts`
- `apps/web-portal/e2e/shell.mobile.spec.ts`
- `apps/web-portal/e2e/handover.mobile.backend.spec.ts`
- `apps/web-crm/src/lib/table-wrapper.test.ts`
- `apps/web-crm/src/lib/no-fixed-width.test.ts`
- `apps/web-portal/src/lib/no-fixed-width.test.ts`
- `apps/web-crm/src/components/shell/Accessibility.axe.test.tsx`
- `apps/web-crm/package.json`
- `pnpm-lock.yaml`
- `scripts/e2e-backend.sh`
- `.github/workflows/ci.yml`
- `docs/acceptance/M31-geraetepruefung.md`
- `apps/web-crm/README.md`
- `apps/web-portal/README.md`

Geteilte Dateien (nur additiv):


Abhängigkeiten:

- WP1 (Testids nav-toggle, Klassen lg:hidden, Sheet und BottomBar)
- WP2 (Testids handover-cards, Schrittchips, PhotoPicker Eingaben, SignatureSheet, Leseansicht, Thumbnail Pfad)
- WP3 (Sweep A vor dem Leeren der Ausnahmeliste, Kalender und Tickets vor dem Entfernen der no-fixed-width Ausnahmen)
- WP5 nur für den Portal Menüeintrag Übergabe im Portal Spec (Assertion bis dahin als test.fixme markiert)

Schritte:

1. playwright.config.ts beider Apps: Projekt chromium bleibt (Desktop Chrome) und erhält grepInvert für /@mobile/; neue Projekte phone ({...devices["Pixel 7"], viewport {width: 390, height: 844}}), tablet (viewport 820x1180, deviceScaleFactor 2, isMobile true, hasTouch true) und tablet-landscape (viewport 1024x768, isMobile true, hasTouch true), alle mit executablePath Spread und grep /@mobile/, damit die 31 bestehenden @backend Specs nicht je Projekt dupliziert werden; grepInvert @backend ohne E2E_BACKEND bleibt; iPhone und iPad Presets bewusst nicht (WebKit fehlt in CI, ci.yml Zeile 186 und 254).
2. e2e/mobile-layout.ts (beide Apps): expectNoHorizontalOverflow(page) prüft elementweise über alle sichtbaren Elemente getBoundingClientRect().right <= innerWidth + 1 und left >= -1 (die Dokumentbreite ist wegen overflow-x-clip am main blind); expectTouchTarget(locator) boundingBox Breite und Höhe >= 44; expectHeaderOneRow(page) Kopfzeile Höhe <= 72; expectCoarsePointer(page) prüft window.matchMedia("(pointer: coarse)").matches in phone und tablet Projekten und scheitert sonst mit Hinweis, weil alle 44 px Assertions an pointer-coarse hängen; expectFontSizeAtLeast(locator, 16).
3. shell.mobile.spec.ts (@mobile, ohne Backend, CRM und Portal): /anmelden ohne Überlauf, Anmeldefeld 44 px und 16 px Schrift im phone Projekt, Kopfzeile eine Zeile; Portal: Manifest, Icons und Service Worker Registrierung wie smoke.spec.ts Zeile 17 bis 46 im Projekt chromium unverändert.
4. handover.mobile.backend.spec.ts (@backend @mobile, test.setTimeout 240 s, uiLogin und apiToken aus e2e/auth.ts): /start mit nav-toggle sichtbar (phone, tablet) beziehungsweise Symbolrail sichtbar (tablet-landscape), Drawer öffnen und mit Escape schließen; /makler/uebergabe mit handover-cards (phone) beziehungsweise Tabelle (tablet); Protokoll per API anlegen (Muster features.backend.spec.ts Zeile 28 bis 41) und öffnen: kein Überlauf, alle Schrittchips >= 44 px, Weiter wechselt und PATCH current_step antwortet 200 auch für Mängel (Response abwarten), Raum anlegen mit Zähler 1, Mangel mit setInputFiles(fixtures/photo.jpg) über die Galerie Eingabe und Status Fertig, Thumbnail Anfrage mit no-store, Zähler mit Wert 1.234,5, Unterschrift von Beteiligtem öffnet das Vollbild, page.mouse Ziehen über den Canvas (Fallback dispatchEvent pointerdown, pointermove, pointerup), Speichern, Karte zeigt unterschrieben am, Abschluss über ConfirmSheet mit force, Leseansicht ohne input Elemente, PDF Link ohne target Attribut; pages.mobile.backend.spec.ts: Kalender Werkzeugleiste, Kontakt Reiter erreichbar, Objekt Einheitenkarten, Ticket Abschnittsnavigation, jeweils Überlauf und Zielgrößen. Portal handover.mobile.backend.spec.ts: Gehilfe per invitePortalUser, /uebergabe/[id] ohne Überlauf, Menüeintrag Übergabe sichtbar (nach WP5), zwei Dateieingaben, Canvas Höhe >= 200.
5. Quelltestwächter: apps/web-crm/src/lib/table-wrapper.test.ts scannt src (ohne .claude/worktrees und Tests) nach <table und verlangt in den sechs Zeilen darüber overflow-x-auto, ui.tableScroll, ui.tableCard oder ResponsiveList; Ausnahmeliste startet mit den 21 Dateien aus WP3 und wird beim Merge von WP3 geleert (Test scheitert, wenn eine Ausnahme nicht mehr nötig ist). no-fixed-width.test.ts: Ausnahmen app/(app)/kalender und components/tickets entfernen nach WP3 Merge; start, bank, banking mit datiertem Kommentar prüfen. Kopie apps/web-portal/src/lib/no-fixed-width.test.ts. Erster axe Test im CRM apps/web-crm/src/components/shell/Accessibility.axe.test.tsx (vitest-axe und axe-core als devDependencies in apps/web-crm/package.json, Lockfile aktualisiert; Test für MobileNav offen, Sheet, BottomBar, StepNav Chips, HandoverSummary Fixture in Tag und Abend per describe.each).
6. scripts/e2e-backend.sh: MHVP_E2E_PW_ARGS dokumentiert für --project phone und --project tablet; ci.yml: web Job unverändert (pnpm e2e läuft alle Projekte, @mobile Smoke Specs etwa plus 1 Minute), e2e-backend Job ruft für das CRM zusätzlich --project phone (nur handover.mobile und pages.mobile, Ziel unter 4 Minuten). Budgetrechnung in docs/plans/M31-handy-tablet.md Abschnitt Tests eintragen: Basis CRM vitest 299 s, Portal 59 s, Backend E2E rund 3 min 12 s plus Build und Seed; Prognose nach WP4 mit gemessenen Werten des ersten Laufs, Budgets 25 und 30 min.
7. docs/acceptance/M31-geraetepruefung.md: Checkliste je Gerät (iPad Safari Hoch und Quer, iPhone Safari, Android Chrome, jeweils Browser und ggf. installiert) mit Ergebnisfeldern und Datum: Fokus Zoom, Kopfzeile eine Zeile, Drawer und Symbolrail, Bodenleiste über Home Indikator und Verhalten bei offener Tastatur (visualViewport), Kamera und Galerie inklusive HEIC, Upload Größe, Thumbnails, Galerie Wischen, Unterschrift beim Drehen, Rückgängig, Same Tab PDF und Zurück, Offline Hinweis, Session Ablauf während einer langen Übergabe (401 Verhalten notieren), Tab Wiederherstellung nach Kamerawechsel. Nicht ausgeführte Punkte werden als nicht ausgeführt eingetragen (Regel 0.1.9).
8. README Abschnitte Tests in apps/web-crm/README.md und apps/web-portal/README.md um die Projekte phone, tablet, tablet-landscape und die Wächter ergänzen; Änderungstext für CHANGELOG im PR (Version 1.45.1 setzt der Integrator).

Tests:

- Playwright Smoke (alle Projekte, nach pnpm build): shell.mobile.spec.ts CRM und Portal grün; bestehende smoke.spec.ts beider Apps im Projekt chromium unverändert grün.
- Playwright @backend @mobile über bash scripts/e2e-backend.sh mit MHVP_E2E_PW_ARGS="--project phone" und einmal "--project tablet" und "--project tablet-landscape": handover.mobile.backend.spec.ts, pages.mobile.backend.spec.ts, Portal handover.mobile.backend.spec.ts grün; Laufzeiten gemessen und im Plan notiert.
- vitest table-wrapper.test.ts, no-fixed-width.test.ts (CRM und Portal), Accessibility.axe.test.tsx CRM in Tag und Abend grün; pnpm -r test grün.
- tsc --noEmit schließt den e2e Ordner ein (tsconfig), make lint grün, pnpm install --frozen-lockfile mit aktualisiertem Lockfile grün.
- Nicht in CI ausführbar und im Bericht als nicht ausgeführt zu melden: WebKit und Safari Läufe; sie laufen über docs/acceptance/M31-geraetepruefung.md.

Abnahme:

- Ein Reviewer kann mit pnpm --filter @mhvp/web-crm exec playwright test --project phone (390 px) und --project tablet (820 px Hoch) sowie --project tablet-landscape (1024 px Quer) die Shell Smoke Specs lokal laufen lassen; jede Assertion nennt Element und Maß im Fehlerfall.
- Die Überlaufprüfung findet einen absichtlich eingebauten Testfall (Element mit w-[500px] auf 390 px) und scheitert; die Zielgrößenprüfung scheitert bei einem Knopf mit min-h-9 ohne pointer-coarse Variante; expectCoarsePointer scheitert im Projekt chromium und besteht in phone und tablet.
- table-wrapper.test.ts scheitert bei einer neuen nackten Tabelle in einer beliebigen Komponente; no-fixed-width.test.ts läuft im Portal.
- CI: web Job unter 25 Minuten, e2e-backend Job unter 30 Minuten mit den zusätzlichen Projekten, Messwerte im Plan eingetragen; Playwright Berichte und Traces werden bei Fehler weiterhin hochgeladen.
- docs/acceptance/M31-geraetepruefung.md liegt vor, ist vom Betreiber auf iPad (Hoch und Quer bei 1024 px Gerät) und iPhone (390 px) ausgefüllt oder trägt den Vermerk nicht ausgeführt je Punkt.

### WP5 Portalangleich für Gehilfen und Beteiligte und CRM als installierbare Hülle (optional, teils betreibergebunden)

Ziel: Mieter und Gehilfen, die das Protokoll auf dem eigenen Handy ausfüllen oder im 14 Tage Lesefenster ansehen, bekommen denselben Foto und Unterschriftskomfort und einen Menüeintrag Übergabe, ohne aus der installierten Portal App geworfen zu werden (M30-06 Umfang unverändert); das CRM lässt sich, wenn der Betreiber M30-08 und die Middleware Ausnahme freigibt, als Hülle ohne Datencache auf dem Home Bildschirm ablegen.

Exklusiv bearbeitete Dateien:

- `apps/web-portal/src/components/handover/HandoverFill.tsx`
- `apps/web-portal/src/components/handover/HandoverFill.test.tsx`
- `apps/web-portal/src/components/handover/SignaturePad.tsx`
- `apps/web-portal/src/components/handover/SignaturePad.test.tsx`
- `apps/web-portal/src/components/handover/PhotoPicker.tsx`
- `apps/web-portal/src/components/handover/PhotoLightbox.tsx`
- `apps/web-portal/src/components/handover/PhotoLightbox.test.tsx`
- `apps/web-portal/src/components/handover/types.ts`
- `apps/web-portal/src/app/(portal)/layout.tsx`
- `apps/web-portal/src/app/(portal)/uebergabe/page.tsx`
- `apps/web-portal/src/app/(portal)/uebergabe/[id]/page.tsx`
- `apps/web-portal/src/app/layout.tsx`
- `apps/web-portal/src/app/manifest.ts`
- `apps/web-portal/src/app/api/portal-files/[...path]/route.ts`
- `apps/web-portal/src/app/api/portal-files/route.test.ts`
- `apps/web-portal/src/components/shell/InstallHint.tsx`
- `apps/web-portal/src/components/shell/InstallHint.test.tsx`
- `apps/web-portal/src/components/shell/PortalNav.tsx`
- `apps/web-portal/src/components/shell/PortalNav.test.tsx`
- `apps/web-portal/src/components/portal/StartTiles.tsx`
- `apps/web-portal/src/components/portal/Accessibility.axe.test.tsx`
- `apps/web-portal/src/lib/ui.ts`
- `apps/web-portal/src/lib/image-downscale.ts`
- `apps/web-portal/e2e/roles.backend.spec.ts`
- `apps/web-portal/public/offline.html`
- `apps/web-crm/src/app/manifest.ts`
- `apps/web-crm/public/sw.js`
- `apps/web-crm/public/offline.html`
- `apps/web-crm/public/icons/icon-192.png`
- `apps/web-crm/public/icons/icon-512.png`
- `apps/web-crm/public/icons/icon-512-maskable.png`
- `apps/web-crm/src/components/shell/PwaRegister.tsx`
- `apps/web-crm/src/components/shell/InstallHint.tsx`
- `apps/web-crm/src/components/shell/InstallHint.test.tsx`
- `apps/web-crm/src/middleware.ts`
- `apps/web-crm/src/middleware.test.ts`
- `apps/web-crm/src/lib/theme.ts`
- `apps/web-crm/e2e/pwa.spec.ts`
- `docs/adr/0014-crm-pwa-shell.md`
- `docs/handbuch/portal.md`
- `docs/handbuch/README.md`

Geteilte Dateien (nur additiv):

- apps/web-portal/messages/de.json (Namensräume Handover.*, Portal.nav.*, Pwa.*, additiv)
- apps/web-portal/messages/en.json (additiv)
- apps/web-crm/messages/de.json (Namensraum Pwa.*, additiv)
- apps/web-crm/messages/en.json (additiv)
- docs/ASSUMPTIONS.md (eine Annahme, additiv)
- apps/web-crm/src/components/shell/UserMenu.tsx (nur nach Merge von WP1: ein Menüeintrag Als App installieren, additiv)
- apps/web-crm/src/app/(app)/layout.tsx (nur nach Merge von WP1: Einbindung PwaRegister, eine Zeile)

Abhängigkeiten:

- WP2 (packages/ui signature-canvas, Portal Thumbnail Endpunkt in portal.py, image-downscale Muster)
- WP1 Merge vor den beiden additiven Änderungen an UserMenu.tsx und (app)/layout.tsx
- Betreiberentscheidungen M30-08 (CRM als installierbare Hülle) und Middleware Ausnahme für den CRM Teil; der Portalteil ist nicht daran gebunden

Schritte:

1. Portal Navigation: (portal)/layout.tsx Zeile 30 bis 61 ergänzt den Eintrag Übergabe (/uebergabe) für Rollen helper, participant, tenant und owner, wenn ein Handover Grant vorliegt (Sichtbarkeit wie StartTiles.tsx Zeile 29, beide Stellen synchron); roles.backend.spec.ts anpassen; PortalNav Einträge bleiben min-h-11.
2. Portal Layout: apps/web-portal/src/app/layout.tsx viewportFit cover und env(safe-area-inset-*) an body und Footer wie apps/web-crm/src/app/layout.tsx Zeile 24 bis 44; manifest.ts theme_color und background_color aus den Tokenwerten (Hex Kopie mit Kommentar auf tokens.css, weil manifest.ts kein CSS liest), maskable Icon ergänzt, shortcuts Übergabe und Meldung; InstallHint.tsx iPadOS Erkennung über navigator.platform MacIntel plus maxTouchPoints > 1; offline.html Text unverändert (keine Daten auf dem Gerät).
3. HandoverFill.tsx: Reiter Zeile 260 bis 272 als tabBar Zwilling (ui.ts Portal erhält tabBar, tab, tabActive, bottomBar, tableScroll bleibt), aria-label des nav auf Abschnitte; PDF Link Zeile 374 und Foto Links Zeile 652 ohne target=_blank (Same Tab beziehungsweise PhotoLightbox); PhotoPicker Zwilling (Kamera und Galerie, accept jpeg, png, heic, heif) mit image-downscale Kopie, Capture first wie im CRM, Status je Datei, Thumbnails über den Portal Thumbnail Endpunkt aus WP2 (portal-files Allowlist erweitern, no-store bleibt); Löschtext mit Fallunterscheidung; Abschluss über ein ConfirmSheet Zwilling statt window.confirm; Portal Umfang M30-06 unverändert (keine internen Felder, keine Versionen, Uploads nur meters, rooms, defects, items). Für Beteiligte im Lesefenster (right read) rendert [id]/page.tsx eine Lesekarte (Kopf, Zähler, Räume mit Mängeln und Fotos, Unterschriften, PDF Link) statt des Ausfüllformulars mit gesperrten Feldern, ohne Felder, die M30-06 ausschließt.
4. Portal SignaturePad.tsx als dünne Hülle über packages/ui signature-canvas (aus WP2) mit Canvas h-56 sm:h-64, Rückgängig, Leeren; Einwilligungstext unverändert; SignaturePad.test.tsx neu; Accessibility.axe.test.tsx um HandoverFill Reiter, PhotoLightbox und SignaturePad in Tag und Abend ergänzen.
5. CRM Hülle (nur nach Betreiberfreigabe M30-08 und der Middleware Ausnahme, sonst dieser Schritt entfällt und wird als nicht umgesetzt gemeldet): manifest.ts (name MH Verwaltungsplattform, short_name MHVP, id und start_url /start, display standalone, Icons 192 und 512 any plus 512 maskable aus dem vorhandenen Markenzeichen mit Rand, theme_color und background_color als Hex Kopie der Tag Tokens mit Kommentar, shortcuts Übergabeprotokolle, Kalender, Tickets); public/sw.js cached ausschließlich offline.html und Icons, Navigationen network first mit 8 s Timeout auf offline.html, nie /api, nie Seiten, Cache Name je Release; offline.html deutsch ("Keine Verbindung. Eingaben werden nicht auf dem Gerät gespeichert."); PwaRegister in (app)/layout.tsx; InstallHint als Eintrag Als App installieren im UserMenu (beforeinstallprompt gemerkt, iOS Hinweis Teilen und Zum Home Bildschirm, iPadOS Erkennung), keine Banner auf jeder Seite; theme.ts setzt <meta name="theme-color"> aus dem aktiven data-theme (Tag oder Abend, berechnet aus getComputedStyle der Variable --mhvp-color-bg, kein Hex im Code); middleware.ts Matcher um sw.js, offline.html, manifest.webmanifest und icons/ erweitern mit middleware.test.ts (Anmeldung weiterhin für alle Seiten und API Pfade erzwungen); vor dem Aktivieren grep nach target=_blank im CRM und Liste im PR (Standalone iOS verliert die Sitzung in externen Tabs).
6. Dokumentation: ADR 0014 CRM als Hülle ohne Datencache (Produktschutz, Spec 3.1 definiert nur das Portal als PWA), docs/ASSUMPTIONS.md Annahme dazu, docs/handbuch/portal.md Abschnitt Übergabe am eigenen Handy (Menü, Fotos, Unterschrift, Lesefenster), docs/handbuch/README.md Abschnitt CRM als App auf Tablet und Handy; Änderungstext für CHANGELOG im PR (Version 1.46.0 setzt der Integrator).

Tests:

- vitest Portal: PortalNav.test.tsx und (portal) Layout Fall Eintrag Übergabe für helper und participant mit Grant, nicht ohne; HandoverFill.test.tsx (Reiter min-h-11, kein target=_blank, zwei Dateieingaben, Capture first Reihenfolge POST vor Upload, Löschtext, ConfirmSheet beim Abschluss, Lesekarte bei right read ohne Eingaben und ohne ausgeschlossene Felder); SignaturePad.test.tsx; PhotoLightbox.test.tsx; InstallHint.test.tsx iPadOS Fall; portal-files route.test.ts Thumbnail Muster mit no-store; Accessibility.axe.test.tsx in beiden Modi ohne Verstöße.
- Playwright Portal: smoke.spec.ts (Manifest, SW, offline.html) unverändert grün; roles.backend.spec.ts mit Eintrag Übergabe; handover.mobile.backend.spec.ts aus WP4 ohne test.fixme.
- vitest CRM: InstallHint.test.tsx (beforeinstallprompt, iPadOS, Dismiss in localStorage mit try/catch), middleware.test.ts (sw.js, offline.html, manifest ohne Sitzung erreichbar, /start und /api/bff weiterhin umgeleitet), theme.ts Test setzt meta theme-color bei Wechsel von data-theme; Playwright e2e/pwa.spec.ts Manifest, Icons, SW Registrierung, offline.html.
- make lint, make typecheck, pnpm -r test; API Tests nicht betroffen (keine Serveränderung in diesem Paket), als nicht ausgeführt melden.

Abnahme:

- 390 px Handy im Portal (Browser und installiert): Menü zeigt für einen Gehilfen den Eintrag Übergabe, das Protokoll ist nach jedem Absprung mit einem Tipp erreichbar; PDF öffnet im selben Tab und Zurück führt zum Protokoll, kein Verlust der Sitzung im installierten Modus; Fotos öffnen in der Lightbox; Kamera und Galerie Eingaben vorhanden, Upload mit Status je Datei; Unterschrift mit Rückgängig, Drehen erhält die Striche; Fußzeile und untere Knöpfe liegen über dem Home Indikator.
- 390 px Portal, Beteiligter im Lesefenster nach Abschluss: Lesekarte ohne Eingabefelder mit Zählern, Räumen, Mängeln, Fotos, Unterschriften und PDF; keine internen Felder, keine Versionen, kein Storno (M30-06).
- 1024 px Tablet (beide Ausrichtungen) im Portal: Reiter in einer Zeile mit 44 px, Felder zweispaltig ab 640 px, Tabellen mit Scrollwrapper; iPad zeigt den Installationshinweis.
- CRM Hülle (nur bei Freigabe): auf Android Chrome und iPad Safari lässt sich das CRM auf dem Home Bildschirm ablegen, startet auf /start im Vollbild ohne Farbsprung, Statusleiste folgt dem Abendmodus, ohne Netz erscheint offline.html; Anwendungsspeicher enthält nach Nutzung keine API Antworten und keine Dokumente (DevTools Application Cache Storage); Anmeldung bleibt für alle Seiten erzwungen.
- Ohne Freigabe: das Paket liefert nur den Portalteil, der CRM Teil steht als nicht umgesetzt im Ergebnisbericht und in docs/OPEN_QUESTIONS.md.

## Offene Entscheidungen des Betreibers

1. M30-07 Offline Erfassung: Soll das Protokoll eine Warteschlange oder einen lokalen Entwurf auf dem Gerät erhalten (personenbezogene Daten, Fotos, Unterschriften auf einem möglicherweise geteilten Tablet, Löschung bei Abmeldung)? Owner Betreiber mit Datenschutz, kein Gate; bis zur Entscheidung online only mit Offline Hinweis und Erneut senden. Entschieden 28.09.2026: vollständig offline mit den Auflagen aus ADR 0016; umgesetzt 29.09.2026 als Regel M30-10 hinter dem Mandantenschalter handover_offline_enabled (Standard aus), Migration 0245, `components/handover/offline/*`, Einstellungen Mandant Schalter Offline Erfassung.
2. Autosave je Feld im Übergabeeditor: Soll der Speichern Knopf in Objekt, Kaution und Teildatensätzen durch feldweises Speichern (PATCH je Feld, mehr handover.updated Ereignisse) ersetzt werden? Owner Betreiber; technisch vorbereitet (Merge Muster dokumentiert), in dieser Welle nicht gebaut.
3. Änderungen nach vorhandener Unterschrift: Der Server erlaubt bis zum Abschluss weiter jede Änderung, auch nachdem ein Beteiligter unterschrieben hat. Soll eine Produktschutzregel Änderungen sperren oder einen Hinweis mit Pflicht zur erneuten Unterschrift verlangen? Owner Betreiber, Rückfrage beim Rechtsanwalt im Rahmen von M30-02; bis dahin unverändert, kein Autosave.
4. Schrittreihenfolge im Editor: Bleibt die heutige Reihenfolge (Objekt, Beteiligte, Kaution, Intern, Zähler, Räume, Mängel, ...) oder wird eine Vor Ort Reihenfolge (Kaution und Intern nach den Vor Ort Schritten) eingeführt, und sollen Mängel zusätzlich im Raum erfasst werden können? Owner Betreiber; Plan behält die heutige Reihenfolge.
5. M30-08 CRM als installierbare Hülle: Freigabe für Manifest, Service Worker (nur Offline Seite und Icons) und die dafür nötige Erweiterung des Middleware Matchers um sw.js, offline.html, manifest.webmanifest und icons/ (Sicherheitsentscheidung, Matcher wurde nach Betreiberbericht bewusst eng gefasst). Owner Betreiber; ohne Freigabe entfällt der CRM Teil von WP5.
6. Thumbnail Caching: Sollen Thumbnails (320 px, ohne Metadaten) mit Cache-Control private, max-age=86400 im Browser des Geräts gehalten werden dürfen, oder bleibt no-store wie auf allen Dateipfaden (mehr Datenverbrauch je Aufruf)? Owner Betreiber mit Datenschutz; Plan setzt no-store.
7. PDF in der App: X-Frame-Options DENY und frame-ancestors 'none' (Next und Traefik) verhindern jeden Inline Viewer. Soll eine dokumentierte Ausnahme für /api/handover-files (M27-02) geprüft werden, oder bleibt es bei Same Tab Anzeige und Download? Zusätzlich: Soll ein Teilen Knopf (navigator.share mit PDF Datei, AirDrop, Mail Anhang, Dateien App) angeboten werden, obwohl das Dokument damit am Postausgang mit Vier Augen Freigabe vorbei weitergegeben wird und ohne Ereignis auf dem Gerät landet? Owner Betreiber; Plan ohne Ausnahme und ohne Teilen.
8. Rail Schwelle: Symbolrail ab 1024 px und volle Rail ab 1280 px (Plan) ändert Laptop Fenster zwischen 1024 und 1279 px gegenüber dem Rail Redesign 1.37. Bestätigen oder volle Rail ab 1024 px behalten (dann bleibt das iPad Querformat bei 704 px Inhalt)? Owner Betreiber.
9. Zähler aus Stammdaten (M30-09): Soll ein Endpunkt Zähler der Einheit und Gemeinschaftszähler in das Protokoll übernehmen, und welche Zuordnung (unit_id, Objektzähler ohne Einheit, Zuordnung meter_type_code zu den Protokollzählerarten) ist die Quelle? Keine Übernahme in meter_reading. Owner Betreiber.
10. Zugriffsprotokollierung beim Einsehen von Beweisen: Sollen Leseansicht, Galerie und Thumbnails ein Ereignis wie document.downloaded erzeugen (6.9.6 gleiche Behandlung aller Pfade), oder bleibt nur der Originalabruf protokolliert? Owner Betreiber; Plan protokolliert Thumbnails nicht, Originalabruf wie heute.
11. Geteiltes Gerät beim Weiterreichen zur Unterschrift: Soll ein eingeschränkter Signiermodus (Navigation und andere Protokolle gesperrt, bis der Mitarbeiter zurücknimmt) und eine kurze Inaktivitätsabmeldung auf Touch Geräten eingeführt werden? Owner Betreiber mit Datenschutz; in dieser Welle nur der Hinweis Gerät übergeben.
12. Foto Provenienz: EXIF wird bewusst entfernt (M30-04), damit fehlt der Aufnahmezeitpunkt; nach einer Wiederholung entspricht created_at dem Upload. Soll File.lastModified als vom Gerät gemeldeter Aufnahmezeitpunkt und der Vermerk clientseitig verkleinert in den Dokumentmetadaten gespeichert werden (API Erweiterung)? Owner Betreiber, Rückfrage Rechtsanwalt zum Beweiswert.
13. Idempotenz wiederholter Uploads: Eine Wiederholung nach Timeout kann doppelte Beweisfotos oder einen 409 bei Unterschriften erzeugen. Soll der Server Dubletten je Protokoll über den SHA-256 des empfangenen Bildes erkennen oder ein Idempotency-Key Header eingeführt werden (API Erweiterung)? Owner Betreiber, Umsetzung nach Entscheidung.
14. Sitzungsdauer gegen Übergabedauer: Eine Übergabe dauert ein bis zwei Stunden; ein Sitzungsablauf mittendrin verwirft Formulare und Striche. Soll die Sitzungs TTL für Touch Geräte angepasst oder eine Neuanmeldung im Sheet mit Erhalt des Zustands gebaut werden? Owner Betreiber mit Sicherheitsbezug (Abschnitt 16).
15. Lesbarkeit: Sollen 11 px Großbuchstaben Labels (mhvp-label), 11 px Tabellenköpfe und text-xs auf Geräten mit grobem Zeiger um eine Stufe (12 auf 13 px) angehoben werden? Wirkt auf beide Apps; Owner Betreiber (Design).
16. Leseansicht im Portal für Beteiligte im 14 Tage Lesefenster: Plan liefert eine Lesekarte im Umfang von M30-06; bestätigen, dass Beteiligte Fotos und Unterschriften aller Beteiligten sehen dürfen (heute sehen sie das Ausfüllformular mit gesperrten Feldern, also dieselben Daten). Owner Betreiber.
17. Aufbewahrungsklasse und Frist für Übergabeprotokolle, Fotos und Unterschriften (V17, M6-04): bleibt offen; die neuen Lese und Thumbnail Pfade legen nichts Neues ab, sind aber an diese Entscheidung zu koppeln. Owner Betreiber mit Steuerberater und Rechtsanwalt, Gates G3 bis G5.
18. Kamera Erfassung für Tickets und DMS: Soll die clientseitige Verkleinerung aus dem Übergabemodul in einer Folgewelle auf Ticket Antworten und DMS Upload ausgeweitet werden (heute dort nur Kamera Eingabe ohne Verkleinerung)? Owner Betreiber, Priorität M21-01.

## Handbuchänderungen

- docs/handbuch/anleitung-mieterwechsel.md, neuer Abschnitt "Übergabe am Tablet oder Handy" (WP2): Anmelden im Browser, Menü über das Symbol links oben (Handy und Tablet hochkant) oder die schmale Leiste links (Tablet quer); Makler, Übergabeprotokolle; Liste als Karten am Handy mit dem Chip Heute; Neu mit Einheit aus dem Bestand oder manueller Adresse; Aufbau des Editors: Schrittleiste zum Wischen mit Zählern und Statuspunkten, unten Zurück und Weiter, Speichern in der unteren Leiste; Rückfrage bei ungespeicherten Eingaben; Objekt und Beteiligte (Telefon, E-Mail und PLZ öffnen die passende Tastatur, Kontaktsuche); Zähler mit Foto aufnehmen oder Aus Galerie wählen (auch iPhone Fotos), Anzeige Wartet, Wird hochgeladen, Fertig, Fehlgeschlagen mit Erneut versuchen; Räume und Mängel: Mangel mit Foto in einem Schritt anlegen; Schlüssel, Gegenstände, Bemerkungen, Anhänge; Unterschriften: Einwilligungstext lesen, Unterschrift von Beteiligtem antippen, Gerät übergeben, Fläche im Vollbild, Rückgängig und Leeren, höchstens eine Unterschrift je Person, nur vor dem Abschluss löschbar; Prüfung und Abschluss mit Zusammenfassung und Hinweisen, Bestätigung, bei Hinweisen trotz Hinweisen; PDF ansehen öffnet im selben Fenster, Zurück führt zum Protokoll; Zustellung vorbereiten erzeugt nur Entwürfe für die Vier Augen Freigabe im Postausgang.
- docs/handbuch/anleitung-mieterwechsel.md, Abschnitt "Protokoll später einsehen" (WP2): abgeschlossene Protokolle öffnen als Leseansicht mit Beteiligten (Anrufen direkt aus der Ansicht), Zählerständen, Räumen mit Mängeln und Fotos, Schlüsseln, Unterschriften mit Zeitpunkt und PDF; Änderungen nur als neue Fassung mit Änderungsgrund; Hinweis, dass Lesestatus und Öffnen kein Zustellnachweis sind.
- docs/handbuch/anleitung-mieterwechsel.md, Abschnitt "Hinweise für den Betrieb vor Ort" (WP2): Eingaben werden nur beim Speichern übertragen; ohne Empfang erscheint der Hinweis Keine Verbindung, Eingaben bleiben auf der Seite bis zum erneuten Speichern, Seite nicht neu laden; Fotos werden vor dem Senden verkleinert, Metadaten werden auf dem Server entfernt; Entfernen eines Fotos löst nur die Verknüpfung dieser Fassung, ohne weitere Fassung wird die Datei endgültig gelöscht; das Gerät beim Unterschreiben nicht unbeaufsichtigt lassen; eine Offline Erfassung ist noch nicht freigegeben (M30-07).
- docs/handbuch/kalender.md (WP3): Knopf Heute springt zum aktuellen Tag; Übergabetermine zeigen am Handy den Knopf Protokoll öffnen; Hinweise Wiederkehrend und Erinnerung stehen als Text in der Zeile; Termin anlegen öffnet am Handy als Bodenblatt.
- docs/handbuch/kontakte.md (WP3): Reiter der Kontaktseite lassen sich am Handy seitlich wischen; Telefonnummern und E-Mail Adressen sind antippbar (Anruf, Mail); Knöpfe Anrufen und E-Mail im Kopf; Einheitenseite zeigt Bewohner als Karten mit denselben Aktionen.
- docs/handbuch/README.md (WP3 und WP5): Abschnitt "Bedienung auf Handy und Tablet" mit den drei Stufen (Handy: Menü über das Symbol, Karten statt Tabellen, Aktionen unten; Tablet hochkant: Menü über das Symbol, volle Breite; Tablet quer: schmale Symbolleiste links, Ausklappen über den Fußknopf), Hinweis, dass Tabellen am Handy seitlich wischbar sind, und, bei Freigabe von M30-08, der Abschnitt "CRM als App auf dem Home Bildschirm" (Menü Konto, Als App installieren; iPad und iPhone über Teilen und Zum Home Bildschirm; die App speichert keine Daten auf dem Gerät, ohne Netz erscheint eine Hinweisseite).
- docs/handbuch/portal.md (WP5): Abschnitt "Übergabeprotokoll am eigenen Handy" für Mieter und Gehilfen: Einladung per QR Code oder Link, Menüeintrag Übergabe, Reiter, Foto aufnehmen oder aus Galerie, Unterschrift mit Rückgängig, Abschluss mit Bestätigung, danach 14 Tage Leseansicht mit PDF im selben Fenster; Hinweis, dass keine Daten auf dem Gerät gespeichert werden und interne Angaben der Verwaltung nicht sichtbar sind.
- docs/handbuch/erfassungsstandards.md, Ergänzung (WP2, ein Absatz): Foto zu Mangel oder Zähler wird direkt beim Anlegen des Eintrags aufgenommen; Standard sind ein Übersichtsfoto je Raum und ein Detailfoto je Mangel; Zählerfoto zeigt Zählernummer und Stand; Fotos werden serverseitig ohne Metadaten gespeichert (keine Ortsangabe).
