# Bedienbarkeitsprüfung CRM Geldfunktionen (1.19 bis 1.22), Stand 26.09.2026

Prüfgegenstand: `apps/web-crm/src/app/(app)/(bank|buchhaltung|abrechnung|rechnungen)/**` und
`apps/web-crm/src/components/(accounting|banking|billing|invoices|receipts)/*`. Geprüft wurden
Bankabgleich (Kennzahlen, Tilgungsbestimmung, Automatik), Zahlläufe und Lastschriften (Vier-Augen,
Gate G2), Mahnwesen (Zahlungserinnerung, Stufen, Vorschau, PDF), Rechnungen und Belegeingang
(E-Rechnung, Widersprüche, automatischer Eingang), Eigentümerabrechnung, Prüfexport sowie die
Berührungspunkte DATEV-Zuordnung und Verwalterhonorar mit XRechnung.

Methode: Codeprüfung aller Seiten und Komponenten, dazu Playwright-Screenshots bei 1280 px und
390 px gegen einen eigenen `next dev` auf Port 3501 mit einer gemockten API (Node-Server auf
Port 3599, Antworten als JSON und RFC-9457-Problem-Details, kein echtes Backend). Prüfkriterien:
Gate-Sperren sichtbar und erklärt (kein toter Button), Beträge `1.234,56 EUR`, Datum `TT.MM.JJJJ`,
Fehlermeldungen aus Problem-Details verständlich, Ladezustände, leere Zustände, Fokus, Tabellen
horizontal scrollbar, keine Gedankenstriche.

Hinweis zur Umgebung: Der Prüfrechner lief parallel mit mehreren Agenten (Lastmittel über 100,
zwei weitere `next dev` auf 3201 und 3401, davon eines mit demselben Build-Ordner `.next-review`,
was beide Server wechselseitig störte); der Dev-Server wurde außerdem zweimal durch den
Speicherwächter beendet. Screenshots bei 1280 px liegen für alle Seiten vor, bei 390 px nur für
einen Teil; die Codeprüfung deckt alle Seiten ab.

## Zusammenfassung

| Bewertung | Anzahl |
| --- | --- |
| behoben | 19 |
| offen | 6 |
| kein Handlungsbedarf | 5 |

Kein Befund betrifft Geldbewegungen, Buchungen oder Gates selbst; alle Gates (G1 bis G4) bleiben
geschlossen und werden von der API geprüft. Die Befunde betreffen Erklärung, Formate, Lade- und
Fehlerzustände und einen fehlenden Bildschirm (Lastschriftläufe).

## Befunde

| Nr. | Seite | Befund | Status |
| --- | --- | --- | --- |
| B01 | /bank/zahlungen | Freigegebene Zahlungsaufträge zeigten keine Erklärung, warum keine Zahlungsdatei angeboten wird (G2). Der Hinweis stand nur oben im Seitentext. | behoben: je Auftrag im Status "freigegeben" der Hinweis "Zahlungsdatei erst mit Freigabestufe G2 ...", `data-testid="gate-g2-hint"`; Freigabezähler als eigene Zeile statt Klammerzusatz. |
| B02 | /bank (neu /bank/lastschriften) | Lastschriftläufe (pain.008, 1.21.0) hatten keine Oberfläche; Vier-Augen-Freigabe, Verwerfen und Dateiablage waren nur über die API erreichbar, die G2-Sperre für den Download nirgends sichtbar. | behoben: neue Seite `/bank/lastschriften` mit Liste (Einzug am, Buchungskreis, Gläubiger, Posten inkl. ausgeschlossene ohne Mandat, Summe, Status, 0 bis 2 Freigaben), Komponente `DirectDebitRunActions` (Freigeben, Datei als Dokument ablegen erst nach zwei Freigaben, Verwerfen mit Rückfrage), kein Download-Button, stattdessen Hinweis "Download und Einreichung erst mit Freigabestufe G2". BFF-Freigaben `GET accounting/direct-debits`, `POST .../{id}/(approve|cancel|file)`. Links von /bank und /bank/zahlungen. Test `DirectDebitRunActions.test.tsx`. |
| B03 | /bank | Kennzahlenkarte zeigte bis zum Eintreffen der Daten nichts (kein Ladezustand). Schwerer: `GET banking/matching-metrics` fehlte in der BFF-Freigabeliste, die Karte konnte im Betrieb nie laden und zeigte stets "Nicht gefunden" (im Screenshot sichtbar). | behoben: BFF-Freigabe ergänzt (Test in `route.test.ts`), Statuszeile "Kennzahlen werden geladen." (`role="status"`), Test ergänzt. |
| B26 | /bank/zahlungen, /bank/lastschriften, Mahnlauf | Bei 390 px liegen die Aktionen ganz rechts in der scrollbaren Tabelle; beim Scrollen ging die Zeilenidentität (Datum, Stufe) verloren. | behoben: fixierte erste Spalte (`mhvp-table--sticky-col`) in den drei Tabellen. |
| B04 | /bank | Tilgungsbestimmung: die Begründungen je Kandidat (Rechnungsnummer, Monat, Betrag) werden angezeigt, der Hinweis der API steht unter der Liste. Kein Befund. | kein Handlungsbedarf |
| B05 | /bank | Automatik-Regeln (7.4): Es gibt keine Oberfläche zum Aktivieren oder Anzeigen von Automatikregeln; der Seitentext erklärt, dass Zuordnungen Vorschläge sind. Die Kennzahlenkarte nennt ausdrücklich "keine Freigabe der Automatik". | offen: Regelanzeige gehört zur Betreiberentscheidung M12-03 (docs/OPEN_QUESTIONS.md); kein toter Button vorhanden. |
| B06 | /rechnungen/[id] | Bankabgleich verlangte die Eingabe einer rohen UUID ("ID des internen Kontos"). Ladefehler wurden verschluckt (Karte blieb unsichtbar). Der Zweck von "Zahlung vorbereiten" (nur Entwurf, G2) war nicht erklärt. | behoben: `BankAccountSelect` mit Suche statt UUID-Feld, Ladezustand und Fehleranzeige aus Problem-Details, Hinweistext zu Entwurf und G2. Test angepasst und ergänzt. |
| B07 | /rechnungen | Bruttovorschau ohne Tausenderpunkt ("Brutto 1234,56 EUR"). | behoben: `formatEur`, Test "1.469,13 EUR". |
| B08 | /rechnungen | "Rechnung erfassen" war ohne Erklärung deaktiviert. | behoben: Hinweis auf die Pflichtangaben, solange der Button deaktiviert ist. |
| B09 | /rechnungen/[id] | Kein Hinweis auf den nächsten Schritt: Freigabe- oder Buchen-Button fehlt je nach Status ohne Erklärung; Positionstabelle ohne Kopfzeile; keine Brotkrume; leere Prüfschrittliste ohne Text. | behoben: "Nächster Schritt" je Zustand (Prüfschritte, IBAN bestätigen, Freigabe zweite Person, Buchen mit G1-Hinweis), Tabellenkopf, `PageHeader` mit Brotkrume, Leertext. Test ergänzt. |
| B10 | /rechnungen/belegeingang | Bei 390 px umbrach der Button "Aus Paperless holen" in drei Zeilen neben dem Eingabefeld. | behoben: Feld und Button untereinander bei schmaler Breite, Button ohne Umbruch. |
| B11 | /rechnungen/belegeingang | E-Rechnung (XRechnung, ZUGFeRD), Widersprüche (XML gegen PDF-Text oder KI) mit Pflichtbestätigung, Quelle je Feld, IBAN nur nach Bestätigung: umgesetzt und verständlich. Die Spalte "Vorschlag" und die Widerspruchszeile zeigten jedoch Rohwerte der API ("2026-09-18", "186.40"). "Rechnung als Entwurf anlegen" war ohne Erklärung deaktiviert. | behoben: `displayValue` formatiert Vorschlagswerte (Beträge `1.234,56 EUR`, Datum `TT.MM.JJJJ`), Eingabefelder behalten das API-Format; Hinweis auf die fehlenden Pflichtangaben und Bestätigungen unter dem Button. Test `displayValue`. |
| B12 | Einstellungen, DMS (automatischer Belegeingang) | Schalter mit Kostenhinweis und Standard aus; Komponente liegt in `components/invoices`, die Seite unter Einstellungen (anderer Prüfbereich). | offen: Seite außerhalb des Bereichs, Komponente ohne Befund. |
| B13 | /buchhaltung/mahnwesen | Ein Fehler beim Laden der Mahnläufe wurde als "Noch keine Mahnläufe" angezeigt. | behoben: Problem-Detail als Alert, leerer Zustand mit Hinweis, wie eine Vorschau entsteht. |
| B14 | /buchhaltung/mahnwesen/[runId] | Stufe 1 (Zahlungserinnerung) zeigte "0,00 EUR" Gebühr statt klarzustellen, dass keine Gebühr anfällt; ohne vorgeschlagene Fälle fehlte jede Erklärung, warum kein Freigabe-Button erscheint; Vier-Augen-Regel stand nicht am Button. | behoben: Stufenbeschriftung "Zahlungserinnerung", Gebühr "keine", Hinweise "Freigabe durch eine andere Person" und "nichts freizugeben", Text bei Lauf ohne Fälle. |
| B15 | /buchhaltung/mahnwesen/einstellungen | Vorschau je Stufe, Zahlungsfrist mit Standardwerten, Sperre Gebühr für Stufe 1 (M16-14) und Objektüberschreibung vorhanden; Speichern nur mit `accounting:approve`. | kein Handlungsbedarf (Screenshot 1280 geprüft, 390 offen) |
| B16 | /buchhaltung/mahnwesen/[runId] | Mahnschreiben als PDF-Entwurf, Ablage als Dokument, Mahnbescheid-Vorbereitung nur auf höchster Stufe, Versand nur als Markierung: vorhanden und erklärt. | kein Handlungsbedarf |
| B17 | /buchhaltung/eigentuemerabrechnung | Ohne Buchungskreis blieb "Abrechnung anlegen" stumm deaktiviert; ein Fehler beim Laden der Buchungskreise wurde nicht angezeigt; keine Brotkrume. | behoben: Alert aus Problem-Details, Hinweistext ohne Buchungskreis, Brotkrume nach Buchhaltung. |
| B18 | /abrechnung | Gleicher Befund wie B17 für Betriebskostenabrechnungen; zusätzlich wurde ein Fehler der Abrechnungsliste als leerer Zustand angezeigt. | behoben: beide Fehler als Alert, Hinweis ohne Buchungskreis. |
| B19 | /abrechnung/[id] | "Ausgeben" setzt G3 voraus; die Sperre war erst nach dem Klick durch die API-Antwort sichtbar. Interne Freigabe ohne Hinweis auf die zweite Person. | behoben: Hinweis unter dem Button (`data-testid="gate-g3-hint"`), Hinweis zur zweiten Person bei "Intern freigeben". Tests ergänzt. |
| B20 | /buchhaltung/[id]/auswertungen | Prüfexport: Formate, SHA-256 verkürzt mit Tooltip, Fehlertext je Lauf, Download nur bei Status "fertig". Der Hinweis "Die Liste aktualisiert sich beim nächsten Laden" verlangt ein manuelles Neuladen. | offen: automatische Aktualisierung (Polling) der Exportliste; kein toter Button. |
| B21 | alle Seiten | Beim Seitenwechsel gab es keinen Ladezustand (Server-Rendering ohne `loading.tsx`); bei langsamer API wirkte die Oberfläche eingefroren. | behoben: `loading.tsx` für /bank, /buchhaltung, /rechnungen, /abrechnung mit gemeinsamer Komponente `components/ui/PageLoading` (Statustext für Screenreader). |
| B22 | Einstellungen, Buchhaltung, DATEV | DATEV-Kontenzuordnung und Verwalterhonorar mit XRechnung liegen unter Einstellungen (`DatevMappingsAdmin`, `BillingSettings`) und gehören zum Prüfbereich eines anderen Agenten. | offen: nicht geprüft (außerhalb des Bereichs). |
| B23 | /bank | Umsatzliste ohne Suche, Filter oder Seitensteuerung (feste 200 Umsätze). | offen: Filter nach Status und Konto, Seitensteuerung; API-Parameter vorhanden, Umsetzung in einem eigenen Schritt. |
| B24 | /bank | "Ignorieren" und "Zuordnen und buchen" arbeiten mit `window.prompt` und `window.confirm`; funktional, aber ohne einheitliches Dialogmuster und ohne Fokusführung. | offen: Dialogkomponente; kein Fehlverhalten. |
| B25 | alle Seiten | Beträge (`formatEur`) und Daten (`formatDate`, `formatDateTime`) einheitlich; im Text keine Gedankenstriche (Prüfung der Seitentexte und `check_i18n.py`). Native Datumsfelder zeigen das Format des Browsers (im Prüfbrowser en-US "mm/dd/yyyy"), im deutschen Browser TT.MM.JJJJ. | kein Handlungsbedarf |

## Geänderte Dateien

- `apps/web-crm/src/app/(app)/bank/page.tsx`, `bank/zahlungen/page.tsx`, neu `bank/lastschriften/page.tsx`, `bank/loading.tsx`
- `apps/web-crm/src/app/(app)/buchhaltung/mahnwesen/page.tsx`, `mahnwesen/[runId]/page.tsx`, `eigentuemerabrechnung/page.tsx`, `buchhaltung/loading.tsx`
- `apps/web-crm/src/app/(app)/rechnungen/[invoiceId]/page.tsx`, `rechnungen/loading.tsx`
- `apps/web-crm/src/app/(app)/abrechnung/page.tsx`, `abrechnung/loading.tsx`
- `apps/web-crm/src/app/api/bff/[...path]/route.ts` (Freigaben Lastschriftläufe und Kennzahlen, + `route.test.ts`)
- `apps/web-crm/src/components/banking/DirectDebitRunActions.tsx` (neu, mit Test), `MatchingMetricsCard.tsx` (+ Test)
- `apps/web-crm/src/components/invoices/InvoiceForms.tsx` (+ Test), `InvoiceMatchPanel.tsx` (+ Test)
- `apps/web-crm/src/components/billing/StatementWorkbench.tsx` (+ Test)
- `apps/web-crm/src/components/receipts/ReceiptIntake.tsx` (+ Test)
- `apps/web-crm/src/components/ui/PageLoading.tsx` (neu)
- `apps/web-crm/messages/de.json`, `messages/en.json` (neue Schlüssel: `DirectDebits`, `Payments.fileLocked`, `Dunning.*Hint`, `Invoices.nextStep`, `InvoiceMatch.*`, `Billing.issueGateHint`, `Shell.loading`, u. a.)

## Tests

- Komponententests des Bereichs (`vitest run` über `components/banking`, `accounting`, `billing`,
  `invoices`, `receipts`, `app/api/bff`, `lib/i18n-consistency.test.ts`): 25 Dateien, 190 Tests
  bestanden, davon neu oder erweitert: `DirectDebitRunActions` (4), `InvoiceMatchPanel` (+1),
  `InvoiceForms` (+2), `StatementWorkbench` (+1), `MatchingMetricsCard` (Ladezustand),
  `ReceiptIntake` (`displayValue`), `route.test.ts` (+5 Freigaben).
- `pnpm typecheck` (web-crm): keine Fehler in den geänderten Dateien; sechs Fehler in
  `components/settings/MembersAdmin.test.tsx` (Feld `reply_approval_required`, Bereich
  Einstellungen eines parallel arbeitenden Agenten, nicht berührt).
- `eslint --max-warnings=0` über die geänderten Ordner: ohne Befund.
- `python3 scripts/check_i18n.py`: OK (Schlüsselparität de/en, keine Gedankenstriche, keine leeren Werte).
- Nicht ausgeführt: der vollständige `vitest`-Lauf (bei einem Versuch 12 fremde Testdateien mit
  Fehlern, unter anderem `tickets/TicketMailThread.test.tsx`, Bereich anderer Agenten) und
  Playwright gegen das echte Backend (`@backend`-Spezifikationen), da kein API-Server lief.

## Offene Punkte

B05, B12, B20, B22, B23, B24 (siehe Tabelle). Keine Betreiberentscheidung erforderlich; B05 hängt an
M12-03.
