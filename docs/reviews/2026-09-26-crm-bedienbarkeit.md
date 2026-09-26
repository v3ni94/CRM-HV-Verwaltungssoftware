# Bedienbarkeitsprüfung CRM, Welle 5 und 6, Stand 26.09.2026

Prüfgegenstand: die neuen CRM-Seiten der Wellen 5 und 6 unter `apps/web-crm/src/app/(app)/(weg|einstellungen|importe|vermietung)/**`
mit den Komponenten unter `components/(hoa|settings|imports|letting|properties|documents)/*`:
WEG (Darlehen, Versicherungsfall, Maßnahme, Überleitung, Einsichtsanfragen, Prüfauftrag, Mehrheitsregeln),
Einstellungen (Automatisierung, Portalformulare, Telefonie, DATEV-Kontenzuordnung, Rechnungsstellung und Steuer),
Importe (Abgleichbericht, Immoware24-Listen), Vermietung (Energieausweis, Exposé-Entwurf), Dokumentdetail,
Objekt (Schwarzes Brett).

Vorgehen: eigener `next dev` auf Port 3301 gegen eine gemockte API (`MHVP_API_INTERNAL_URL` auf einen
lokalen Node-Server mit festen Antworten, Sitzungscookies gesetzt), Playwright-Screenshots bei 1280 px und
390 px, dazu automatische Prüfung je Seite auf horizontales Scrollen, Gedankenstriche, rohe ISO-Daten und
rohe Dezimalbeträge im Seitentext sowie Konsolenfehler. Ergänzend Codeprüfung der Komponenten auf
Formularvalidierung, Lade- und Leerzustände, Erfolgsmeldungen, Fokus nach Aktionen, Schaltflächen aus
`lib/ui.ts` und Rückfragen bei Löschen und Beenden. Dies ist ein Review, keine Freigabe; Screenshots liegen
nicht im Repository.

Kriterien: klare Fehlermeldungen, Ladezustände, leere Zustände, Erfolgsmeldungen, Fokus nach Aktionen,
Tabellen scrollbar, Beträge 1.234,56 EUR, Datum TT.MM.JJJJ, keine Gedankenstriche, Schaltflächen aus
`lib/ui.ts`, Rückfrage bei Löschen und Beenden.

## Zusammenfassung

| Schweregrad | Anzahl | davon behoben |
| --- | --- | --- |
| hoch (Seite nicht nutzbar) | 2 | 2 |
| mittel (Format, Rückmeldung fehlt) | 12 | 12 |
| niedrig (Kosmetik, Konsistenz) | 8 | 6 |

Die Kriterien Gedankenstriche (keine gefunden), horizontales Scrollen bei 390 px (keines gefunden) und
Rückfragen bei Löschen und Beenden (Automatisierung, Portalformulare, DATEV, Mehrheitsregeln, Schwarzes Brett,
Immoware24-Listen mit `window.confirm`) waren auf allen geprüften Seiten erfüllt.

## Befunde

| Nr. | Seite | Befund | Schwere | Status |
| --- | --- | --- | --- | --- |
| H1 | WEG Prüfauftrag | Seite bricht mit Serverfehler ab: `formatDate` wurde als Funktion an die Client-Komponente `BoardAuditPanel` übergeben (in React Server Components nicht erlaubt), zusätzlich `t("audit.status")` auf einem Nachrichtenobjekt (INSUFFICIENT_PATH). | hoch | behoben: `BoardAuditPanel` importiert `formatDate` selbst, neuer Schlüssel `HoaWork.audit.statusLabel`, Gesamtstatus wird übersetzt, Tabelle in `overflow-x-auto`. |
| H2 | Objekt (Schwarzes Brett, Objektseite) | `t("status")` in `objekte/[propertyId]/page.tsx` zeigt auf ein Nachrichtenobjekt; im Entwicklungsmodus Fehlerüberlagerung, produktiv Schlüsselpfad statt Beschriftung. | hoch | behoben: neuer Schlüssel `Properties.statusLabel`. |
| M1 | Vermietung Exposé | Angebotsmiete roh (`850.00`), Ausweisdaten roh (`2020-03-01`), Wohnfläche `75.50`, Art `apartment`, Ausweisart `verbrauch`. | mittel | behoben: Formatierung je Feld (EUR, TT.MM.JJJJ, m², übersetzte Codes). |
| M2 | WEG Darlehen | Kennzahlen (`dl` mit 3 Spalten) bei 1280 px verschoben, Beschriftung und Wert liefen auseinander; Zinssatz roh `3.5` statt `3,50 %`; Positionstabelle ohne Kopfzeile und ohne Leerzustand. | mittel | behoben. |
| M3 | WEG Versicherungsfall | Kennzahlen wie M2; Positionstabelle ohne Kopfzeile und Leerzustand. | mittel | behoben. |
| M4 | WEG Maßnahme | Finanzierungstabelle ohne Kopfzeile und Leerzustand. | mittel | behoben. |
| M5 | WEG Darlehen, Versicherung, Maßnahme, Überleitung (`FinanceForms`) | Schaltflächen nur deaktiviert, ohne Hinweis, welches Feld fehlt oder falsch formatiert ist; keine Erfolgsmeldung; kein Fokus nach dem Erfassen; Primäraktion als Sekundärschaltfläche. | mittel | behoben: Hinweis unter dem Formular (fehlende Felder, Betragsformat, `aria-invalid`), Status "Wird gespeichert." und "Gespeichert." (`role="status"`), Fokus zurück auf Datum bzw. Betrag, `ui.primary`. |
| M6 | WEG Einsichtsanfragen (Liste) | Tabelle nicht in `overflow-x-auto`. | mittel | behoben. |
| M7 | WEG Einsichtsanfrage erfassen | Schaltfläche stumm deaktiviert; kein Hinweis auf Antragsteller, Datum, Umfang. | mittel | behoben: schrittweiser Hinweis, `ui.primary`. |
| M8 | WEG Einsichtsanfrage (Detail) | Nach Statusschritt, Vermerk und Paket nur Seitenneuladen ohne Bestätigung. | mittel | behoben: "Gespeichert." als `role="status"`. |
| M9 | Einstellungen Automatisierung | Zeitstempel im Protokoll über `toLocaleString("de-DE")` (`25.9.2026, 07:05:00`) statt `TT.MM.JJJJ HH:MM`; Protokolltabelle nicht scrollbar. | mittel | behoben: `formatDateTime`, `overflow-x-auto`. |
| M10 | Einstellungen Rechnungsstellung und Steuer | Keine Validierung vor dem Speichern (Rechnungskürzel, Sachkontenlänge, Wirtschaftsjahresbeginn); Meldungen als `span` ohne `role`. | mittel | behoben: Prüfung mit den vorhandenen Validierungstexten, `role="status"` und `role="alert"`, Schaltfläche in `formActions`. |
| M11 | Importe Abgleichbericht | Bei Fehler der Listenabfrage blieb "Berichte werden geladen." dauerhaft neben der Fehlermeldung stehen. | mittel | behoben: Leerzustand nach Fehler, Ladezustand endet. |
| M12 | Objekt Schwarzes Brett | Keine Erfolgsmeldung nach Anlegen, Speichern und Beenden. | mittel | behoben: "Aushang gespeichert." und "Aushang beendet." als `role="status"`. |
| N1 | Einstellungen Portalformulare | Keine Erfolgsmeldung nach Speichern und Aktivieren; Umschalten und Löschen ohne Sperre gegen Doppelklick; Abbrechen während des Speicherns möglich. | niedrig | behoben. |
| N2 | Einstellungen Telefonie | Erfolgsmeldung ohne `role="status"`. | niedrig | behoben. |
| N3 | WEG Prüfauftrag (Beiratszugang) | Keine Bestätigung nach Antwort oder Zugangsvergabe; Primäraktion als Sekundärschaltfläche. | niedrig | behoben. |
| N4 | Einstellungen WEG Mehrheitsregeln | Schaltfläche stumm deaktiviert (Fundstelle unter 3 Zeichen); eigene Mehrheit ohne Prüfung von Zähler und Nenner; keine Erfolgsmeldung. | niedrig | behoben: Hinweistexte, Prüfung Zähler und Nenner, "Gespeichert.". |
| N5 | Vermietung Energieausweis | Kennwert, Baujahr und Gültigkeit ohne Prüfung; Komma im Kennwert ging unverändert an die API; Effizienzklasse nicht normiert; Erfolgsmeldung ohne `role`. | niedrig | behoben. |
| N6 | Einstellungen DATEV, Importe Immoware24-Listen, Dokumentdetail, Telefonie | Keine Auffälligkeiten: Leerzustände, Rückfragen, Erfolgs- und Fehlermeldungen vorhanden, Tabellen scrollbar, Daten und Beträge formatiert. | niedrig | kein Handlungsbedarf. |
| N8 | WEG Prüfauftrag | Gesamtstatus wird nur übersetzt, wenn der Wert in `HoaWork.audit.status` oder `audit.itemStatus` vorkommt; andere Werte der API (zum Beispiel `in_progress`) erscheinen roh. | niedrig | offen: Wertemenge von `overall_status` in der API klären und Schlüssel ergänzen (Seite wird parallel für A72 umgebaut). |
| N7 | Alle Seiten | Datumsfelder (`type="date"`) zeigen im Chromium der Prüfumgebung `mm/dd/yyyy`; die Darstellung folgt der Browsersprache, nicht der Anwendung. | niedrig | offen (browserabhängig, kein Codebefund; ein eigenes Datumsfeld wäre ein größerer Umbau). |

## Nicht geprüft oder nur eingeschränkt

- Die Prüfumgebung war durch parallele Agenten stark ausgelastet (Load über 100); der `next dev` auf Port 3301
  lieferte zeitweise 404 oder 500 durch Neukompilierung. Nach den Korrekturen wurden Darlehen, Einsicht,
  Prüfauftrag, Abgleich, Mehrheitsregeln und Automatisierung bei 1280 px und 390 px erneut aufgenommen und
  bestätigt; Versicherungsfall, Maßnahme und Exposé konnten nach der Korrektur nur teilweise erneut aufgenommen
  werden und sind über die Komponententests und die Typprüfung abgesichert.

- Playwright-Screenshots wurden gegen gemockte Antworten aufgenommen; Geschäftslogik der API (Statuswechsel,
  Gates) ist nicht Gegenstand dieser Prüfung.
- Die Seiten Einstellungen Mandant (`CompanySettings`) und Kalender waren nicht Teil des Auftrags; die
  Mandantenseite fiel im Mock wegen einer abweichenden Antwortform aus und wurde nicht bewertet.
- Parallel arbeitende Agenten hatten nicht committete Änderungen an `pruefung/[auditId]/page.tsx`
  (Positionsauswahl, Prüfberichte) und `PortalFormsAdmin.tsx` (Einreichungen); die Befunde H1 und N1 wurden
  mit minimalen Änderungen auf diesem Arbeitsstand behoben.

## Ergänzte Komponententests

- `hoa/FinanceForms.test.tsx`: Hinweis bei falschem Betragsformat und fehlenden Feldern, Erfolgsmeldung und
  Fokus nach dem Erfassen, fehlende Darlehensfelder, API-Fehler beim Statuswechsel.
- `hoa/InspectionRequests.test.tsx` (neu): schrittweise Hinweise bis zur Erfassung.
- `hoa/InspectionPanel.test.tsx`, `hoa/BoardAuditPanel.test.tsx`: Erfolgsmeldung, Datumsformat ohne Funktionsprop.
- `settings/MajorityRulesAdmin.test.tsx`: Hinweis Fundstelle, ungültiger Bruch, Erfolgsmeldung.
- `settings/BillingSettings.test.tsx`: Validierung vor dem API-Aufruf.
- `settings/PortalFormsAdmin.test.tsx`: Erfolgs- und Fehlermeldung beim Umschalten.
- `properties/EnergyCertificateForm.test.tsx`: Validierung Baujahr und Gültigkeit, Dezimal und Klasse normiert.
- `properties/PropertyNotices.test.tsx`: Rückfrage vor Beenden, Erfolgsmeldung.
- `imports/ReconciliationReports.test.tsx`: Ladezustand endet bei Fehler.
