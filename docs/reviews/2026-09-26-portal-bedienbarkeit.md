# Bedienbarkeits- und Mobilprüfung Portal, Stand 26.09.2026

Prüfgegenstand: alle Seiten von `apps/web-portal` (Mieter, Eigentümer, Beirat, Dienstleister,
Anmeldung, Einladung), Schwerpunkt Welle 6: Beschlüsse, Ansprechpartner, Hausgeldkonto, Aushänge,
Formulare, Prüfungsraum des Beirats, Meldungen mit Fotos und Terminvorschlägen, Aufträge, Einladung,
Installationshinweis (PWA).

Vorgehen: `next dev` auf Port 3211 gegen einen lokalen Mock der Portal-API (Port 3911, Rollen
Eigentümer mit Beirat, Mieter, Dienstleister, leerer Datenbestand, API nicht erreichbar).
Playwright-Screenshots bei 360 px Breite (Chromium, Locale de-DE), automatische Messung von
Seitenbreite, überstehenden Elementen, Tabellenbreite, unbeschrifteten Bedienelementen und
Überschriftenstruktur, Tastaturdurchlauf (Tab-Reihenfolge) auf Formularen, Anmeldung und
Übersicht, Auslösen der Validierungs- und API-Fehler (422, 404, keine API).

Nicht geprüft: Übergabeprotokoll (`/uebergabe`, Bestandsseite aus Welle 3, hat eigene Tests), echte
Geräte (iOS Safari Installationshinweis nur per User-Agent simuliert), Screenreader-Ausgabe
(nur Rollen und Beschriftungen im DOM geprüft), Kontrast messtechnisch (Token aus `@mhvp/ui`,
Sichtprüfung der Screenshots ohne Befund).

Dies ist eine Bedienbarkeitsprüfung, keine Freigabe. Verhalten und API wurden nicht geändert.

## Zusammenfassung

| Ergebnis | Anzahl |
| --- | --- |
| behoben | 17 |
| offen | 6 |
| ohne Befund | 9 Seiten |

## Befunde

| Nr. | Seite | Befund | Status |
| --- | --- | --- | --- |
| B01 | Hausgeldkonto | Tabelle 517 px breit, ganze Seite scrollt horizontal (Seitenbreite 550 px statt 360 px); Kopfzeile und Beträge laufen aus dem Kartenrahmen. | behoben: Scrollcontainer `ui.tableScroll` nur um die Tabelle, erste Spalte (Buchungsdatum) bleibt beim seitlichen Scrollen stehen (`mhvp-table--sticky-col`), Karte bleibt im Raster. |
| B02 | Hausgeldkonto | Beträge linksbündig, "300,00 EUR" bricht in zwei Zeilen um. | behoben: Klasse `num` (rechtsbündig, Tabellenziffern) und `whitespace-nowrap` für Beträge und Daten, Summenblock rechtsbündig ohne Umbruch. |
| B03 | Hausgeldkonto | Stornierte Buchungen nur durch Durchstreichen erkennbar (nicht für Screenreader, schwacher Kontrast). | behoben: zusätzlicher Text "(storniert)" nur für Screenreader (`sr-only`). |
| B04 | Hausgeldkonto | Tabelle ohne Beschriftung, Spaltenköpfe ohne `scope`. | behoben: `caption` (unsichtbar), `scope="col"`, Abschnitt mit `aria-labelledby` je Vertrag. |
| B05 | Prüfung Beirat (Detail) | Tabelle Abrechnungspositionen 442 px breit, Seite scrollt horizontal; Beträge brechen um ("12.345,67 / EUR"). | behoben: Scrollcontainer, `num` und `whitespace-nowrap`, `caption`, `scope="col"`. |
| B06 | Prüfung Beirat (Liste und Detail) | Gesamtstatus wird roh aus der API angezeigt ("open" statt "Offen"); das Wort "bis" im Zeitraum ist im Code fest verdrahtet. | behoben: Übersetzung über `Audit.status.*` mit Rückfall auf den Rohwert, neuer Schlüssel `Audit.periodRange`. |
| B07 | Prüfung Beirat (Detail) | Unbekannte Werte von `sampling` oder `kind` würden `t()` mit fehlendem Schlüssel aufrufen. | behoben: Rückfall auf den Rohwert, wie bereits bei Beschlüssen. |
| B08 | Meldung (Detail) | Langer Dateiname eines Anhangs bricht nicht um, Seite scrollt horizontal (379 px). | behoben: Anhänge als Liste mit `break-all` und `aria-label`. |
| B09 | Auftrag (Detail) | Angebotsbetrag roh "1234.5 EUR" statt "1.234,50 EUR". | behoben: `formatEur`. |
| B10 | Auftrag (Detail) | Seite ohne `h1`; Auftragsbeschreibung nur als `span`. | behoben: `h1` (unsichtbarer Vorsatz "Auftrag:"), Status mit Rückfall auf Rohwert. |
| B11 | Auftrag (Detail) | Leeres Angebot, fehlender Termin, leerer Ausführungsbericht und unvollständige Rechnung wurden ohne Meldung verworfen (Klick ohne Reaktion). | behoben: Fehlermeldungen `Orders.quoteAmountRequired`, `appointmentRequired`, `reportRequired`, `invoiceFieldsRequired` als `role="alert"`; Pflichtfelder mit `aria-required`; Formulare mit `noValidate` und `aria-busy`. |
| B12 | Formulare | Nach Öffnen eines Formulars verschwindet der auslösende Button, der Fokus fällt auf `body` (Tastatur und Screenreader verlieren die Position). | behoben: Fokus springt auf die Überschrift des Formulars (`tabIndex=-1`). |
| B13 | Formulare | Pflichtfelder nur durch "*" markiert, ohne Erklärung und ohne `aria-required`. | behoben: Hinweis `Forms.requiredHint`, `aria-required` je Feld, `aria-expanded` am Öffnen-Button. |
| B14 | Meldungen, Meldung, Auftrag, Prüfung, Terminvorschläge | Erfolgsmeldungen ohne `role="status"`, werden von Screenreadern nicht angesagt. | behoben: `role="status"` auf allen Erfolgsmeldungen; Bestätigen-Button je Terminvorschlag mit `aria-describedby` auf den Termin. |
| B15 | Neue Meldung | Titel und Beschreibung ohne `aria-required`, Fotohinweis nicht mit dem Feld verknüpft. | behoben: `aria-required`, `aria-describedby`, `aria-labelledby` am Formular, `aria-busy` während des Sendens. |
| B16 | Alle Seiten | Bei API-Fehler (z. B. API nicht erreichbar) erscheint die englische Standardfehlerseite von Next.js; bei unbekannter Meldung oder Auftrag die Standard-404-Seite; kein Ladezustand. | behoben: `error.tsx` (deutscher Hinweis, "Erneut versuchen", "Zur Übersicht", keine technischen Details), `not-found.tsx`, `loading.tsx` (Live-Region und Platzhalter) im Bereich `(portal)`. |
| B17 | Layout, Ansprechpartner | Navigation ohne `aria-label`; Navigations- und Telefonlinks unter 36 px Höhe (Touchziel), kein sichtbarer Fokusring. | behoben: `aria-label` "Hauptnavigation", Mindesthöhe 36 px, Fokusring in Gold. |
| B18 | Aushänge, Beschlüsse, Ansprechpartner | Lange Titel und Namen ohne Umbruchregel (Risiko bei sehr langen Wörtern). | behoben: `break-words`. |
| O01 | Hausgeldkonto | Auch mit Scrollcontainer sind bei 360 px die Betragsspalten erst nach seitlichem Scrollen sichtbar; es gibt keinen sichtbaren Hinweis auf den Scrollbereich. Eine Kartenansicht je Buchung wäre auf dem Telefon lesbarer, ändert aber die Darstellung. | behoben 26.09.2026: unterhalb von `md` Karte je Buchung (Datum, Buchungstext, Art, Betrag rechts, Saldo danach), ab `md` unverändert die Tabelle; Umschalten rein über den CSS Breakpoint, Stornos weiterhin durchgestrichen mit Hinweis für Vorleseprogramme (`HoaAccountTable.tsx`, `OwnerPages.test.tsx`, `PortalStates.test.tsx`) |
| O02 | Layout | Die Navigation ist bei 360 px vier bis sechs Zeilen hoch (Eigentümer mit Beirat: zehn Einträge) und verdrängt den Inhalt; keine aktive Markierung der aktuellen Seite. Ein einklappbares Menü oder eine Fußleiste wäre die mobile Lösung. | behoben 26.09.2026: unterhalb von `md` einklappbares Menü mit Schaltfläche (`aria-expanded`, `aria-controls`), Escape und Seitenwechsel schließen, keine Fokusfalle; ab `md` unverändert horizontal; aktive Seite mit `aria-current="page"` markiert (`components/shell/PortalNav.tsx`, `PortalNav.test.tsx`, Layout `(portal)/layout.tsx`) |
| O03 | Auftrag (Detail) | Alle fünf Formulare (Angebot, Terminvorschläge, Termin, Ausführung, Rechnung) sind unabhängig vom Auftragsstatus immer sichtbar; auf dem Telefon sehr lange Seite, Dienstleister sieht z. B. "Rechnung einreichen" bei Status "Angefragt". Ausblenden nach Status ist eine fachliche Entscheidung (M22). | offen |
| O04 | Auftrag (Detail) | Datumsfelder (`datetime-local`, `date`) zeigen das Browserformat (im Test "mm/dd/yyyy"), nicht TT.MM.JJJJ; abhängig von Gerätesprache, im Code nicht änderbar ohne eigene Datumseingabe. | offen, Hinweis Handbuch |
| O05 | Prüfung Beirat (Detail) | Der Absenden-Button ist bei leerem Text deaktiviert; Tastaturnutzer erhalten keinen Hinweis, warum. Aktivieren mit Fehlermeldung wäre konsistenter zu den übrigen Formularen, ändert aber das Verhalten. | offen |
| O06 | Anmeldung, Einladung | Der Installationshinweis (PWA) erscheint nur nach `beforeinstallprompt` oder auf iOS; auf Desktop-Chromium ohne Ereignis nicht sichtbar, daher hier nur per Komponententest geprüft (`InstallHint.test.tsx`). | offen, Prüfung auf Gerät |

Ohne Befund bei 360 px: Übersicht (alle Rollen), Aushänge, Meldungen (Liste), Formulare (Liste),
Beschlüsse, Ansprechpartner, Prüfung Beirat (Liste), Aufträge (Liste), Kontoauszug (Tabelle 344 px,
vorsorglich mit Scrollcontainer und `num` versehen), Dokumente, Zählerstand, Datenänderung,
Anmeldung, Einladung. Leere Zustände aller Listen zeigen den jeweiligen Hinweis; 403 für Mieter auf
Eigentümerseiten zeigt "Diese Seite steht nur Eigentümern zur Verfügung". Datumsformat TT.MM.JJJJ und
Beträge 1.234,56 EUR auf allen Seiten korrekt (nach B02, B05, B09).

## Geänderte Dateien

- `apps/web-portal/src/lib/ui.ts` (`tableScroll`, `tableStickyCol`, `srOnly`)
- `apps/web-portal/src/components/portal/HoaAccountTable.tsx`, `BoardEngagementDetail.tsx`,
  `WorkOrderDetail.tsx`, `PortalForms.tsx`, `NewTicket.tsx`, `TicketComments.tsx`,
  `AppointmentProposals.tsx`, `PropertyContactList.tsx`, `ResolutionList.tsx`, `NoticeList.tsx`
- `apps/web-portal/src/components/auth/InvitationForm.tsx`
- `apps/web-portal/src/app/(portal)/layout.tsx`, `konto/page.tsx`, `pruefung/page.tsx`,
  `meldungen/[id]/page.tsx`; neu: `error.tsx`, `loading.tsx`, `not-found.tsx`
- `apps/web-portal/messages/de.json`, `en.json` (nur neue Schlüssel)
- `apps/web-portal/eslint.config.mjs` (Build-Ordner `.next-*/**` wie in `.gitignore` von ESLint ausgenommen; ohne
  das schlug `pnpm -r lint` an den Build-Artefakten eines parallelen E2E-Laufs fehl)
- Tests neu: `src/components/portal/PortalStates.test.tsx` (11 Fälle), `src/app/(portal)/error.test.tsx`

## Testlauf

Siehe Ergebnisbericht der Aufgabe (`pnpm --filter @mhvp/web-portal test`, `pnpm typecheck`,
`pnpm -r lint`, `python3 scripts/check_i18n.py`). Playwright-Screenshots liegen nur im
Arbeitsverzeichnis des Prüflaufs, nicht im Repository.
