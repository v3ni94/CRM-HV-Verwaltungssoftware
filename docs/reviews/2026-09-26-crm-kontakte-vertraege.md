# Bedienbarkeitsprüfung Kontakte und Dienstleisterverträge (Funktionen aus 1.22), Stand 26.09.2026

Prüfgegenstand: `apps/web-crm/src/app/(app)/kontakte/**`, `apps/web-crm/src/components/contacts/*`
(IBAN-Freigabe `BankAccountApproval.tsx`, Anrufliste `CallsPanel.tsx`, Kontaktliste),
`apps/web-crm/src/components/contracts/ServiceContracts.tsx` (Dienstleisterverträge, Seite
`dienstleistervertraege/page.tsx` nur lesend geprüft). Bewertet gegen `docs/MASTER-PROMPT.md`
6.6 (Kontakte), 13.5 (Telefonie, A70), M5-01 (Vier-Augen-Freigabe IBAN), M9-06 (Dienstleisterverträge, A41).

Vorgehen: Prüfung mit eigenem `next` auf Port 3401 gegen einen gemockten API-Server (Port 8401,
`auth/me`, `contacts`, `contacts/{id}`, `calls`, `service-contracts`, `properties`, Freigabe- und
Vorschlagsendpunkte), Playwright-Screenshots bei 1280 px und 390 px, Interaktion Ablehnung mit
Begründung. Keine API-Änderung (Performance-Agent arbeitet parallel an `mhvp/contacts` und
`mhvp/contracts`). Dies ist ein Review mit Nachbesserung, keine Freigabe.

Hinweis zur Umgebung: Der `next dev`-Server lief parallel zu drei weiteren Dev-Servern anderer Agenten
auf demselben Quellbaum und lieferte nach Hot Reloads wiederholt 404 oder leere Seiten; Dev-Server und
Mock wurden zudem mehrfach von außen beendet, ein Produktions-Build scheiterte an parallel geänderten
Dateien. Geprüft und per Screenshot belegt sind: Kontaktliste 1280 und 390 px (vorher und nachher),
Bankverbindungen 1280 und 390 px (vorher und nachher, Ablehnung mit Begründung durchgespielt, Antwort
der API mit `reason` im Mock-Protokoll bestätigt), Anrufe 1280 px (vorher und nachher) und 390 px
(vorher), Dienstleisterverträge 1280 px (vorher und nachher) und 390 px (vorher). Die Kartenansichten
für Anrufe und Dienstleisterverträge bei 390 px sind nach der Nachbesserung durch Komponententests
(`service-contracts-cards`) abgedeckt, ein abschließender Screenshot bei 390 px konnte in dieser
Umgebung nicht mehr erstellt werden; bitte auf Staging nachprüfen.

## Zusammenfassung

| Schweregrad | Anzahl | behoben |
| --- | --- | --- |
| hoch | 2 | 2 |
| mittel | 6 | 5 |
| niedrig | 5 | 3 |

## Befunde

### IBAN-Freigabe im Vier-Augen-Prinzip (BankAccountApproval)

| Nr. | Schwere | Befund | Status |
| --- | --- | --- | --- |
| B1 | hoch | Bei 390 px lag die Spalte "Freigabe" (Status, Buttons) außerhalb des sichtbaren Bereichs der horizontal scrollenden Tabelle. Der Freigabestatus war auf dem Telefon nicht erkennbar, die Freigabe nicht bedienbar. | behoben: Kartenliste unter `sm` (`data-testid="bank-accounts-cards"`) mit IBAN, Bank, Inhaber, Gültigkeit und Freigabeblock; Tabelle ab `sm`. |
| B2 | hoch | Ablehnung nur über `window.confirm` ohne Begründung, obwohl die API `BankAccountDecisionIn.reason` (max. 500 Zeichen) annimmt und ins Ereignisprotokoll schreibt. Eine Ablehnung ohne Grund ist für den Erfasser nicht nachvollziehbar. | behoben: Inline-Formular "Begründung der Ablehnung" (Pflichtfeld, max. 500 Zeichen, Hilfetext), Bestätigen und Abbrechen; die Begründung geht als `reason` an `POST .../reject`. |
| B3 | mittel | Kein Entscheidungsdatum am Status "freigegeben" und "abgelehnt"; `decided_at` war in der Antwort vorhanden, wurde aber nicht angezeigt. | behoben: "am TT.MM.JJJJ HH:MM" neben dem Status. |
| B4 | mittel | Keine Rückmeldung nach Freigabe oder Ablehnung; die Seite wurde nur per `router.refresh()` neu geladen. Bei langsamer Antwort blieb unklar, ob die Aktion gewirkt hat. | behoben: Statusmeldung (`role="status"`) "IBAN … freigegeben." bzw. "… abgelehnt."; der Zustand wird sofort aus der API-Antwort übernommen. |
| B5 | mittel | Ohne Recht `contacts:approve` fehlte jeder Hinweis, warum keine Buttons erscheinen. Plattformadministratoren sahen die Buttons, die API lehnt sie aber ab (`services.decide_bank_account`, `is_platform_admin`). | behoben: Hinweistexte "Freigabe nur mit Recht contacts:approve durch eine zweite Person" und "Plattformadministratoren geben keine IBAN frei…"; neue Prop `isPlatformAdmin` aus `auth/me`. |
| B6 | niedrig | Maskierte IBAN brach in der Tabelle in mehrere Zeilen um (`font-mono` mit Leerzeichen). | behoben: `whitespace-nowrap`, Zeilen `align-top`. |
| B7 | niedrig | In der Kontaktliste ist nicht erkennbar, ob ein Kontakt eine IBAN "zur Freigabe" hat; `ContactSummary` liefert kein entsprechendes Feld. Eine Freigabeübersicht fehlt (Tagesübersicht A40 wäre der passende Ort). | offen: API-Erweiterung (`pending_bank_approvals` in `ContactSummary` oder Zähler in `workspace/digest`), Eigentümer Betreiber, kein Gate betroffen. |

Die Regel "Ersteller darf nicht selbst freigeben" bleibt doppelt gesichert: die Oberfläche blendet die
Buttons für `requested_by === user_id` aus und zeigt "selbst erfasst, Freigabe durch eine andere Person",
die API antwortet mit `gate_four_eyes` (409). Der API-Fehlertext wird jetzt in der Zeile angezeigt
(Test "shows the API problem detail when the release is refused").

### Anrufliste (CallsPanel)

| Nr. | Schwere | Befund | Status |
| --- | --- | --- | --- |
| C1 | mittel | "Verwerfen" war für jede Person sichtbar, die API verlangt `communication:update` (`telephony.dismiss_proposal`). Klick führte zu 403. | behoben: Prop `canDismiss` (Seite übergibt `communication:update`), ohne Recht ein Hinweis statt Button. |
| C2 | mittel | Verwerfen ohne Rückfrage und ohne sofortige Rückmeldung; erst nach dem Neuladen erschien "Vorschlag verworfen." | behoben: Rückfrage "Vorschlag Rückruf wirklich verwerfen? Es wird kein Ticket angelegt." und lokaler Zustand, die Meldung erscheint sofort. |
| C3 | niedrig | "Rufnummer maskiert" ohne Erklärung. | behoben: Tooltip "Vollständige Rufnummer nur mit Recht contacts:read." |
| C4 | niedrig | Maskierung: die Oberfläche zeigt, was die API liefert (`number_masked`, `mask_number`); ohne `contacts:read` kommt die Nummer bereits maskiert an, ein Klartext ist im Browser nie vorhanden. Kein Befund, zur Dokumentation. | kein Handlungsbedarf |

Annehmen legt weiterhin nur nach Klick ein Ticket an (`tickets:create`), "Ticket 42 angelegt." erscheint
direkt aus der Antwort.

### Dienstleisterverträge (ServiceContracts)

| Nr. | Schwere | Befund | Status |
| --- | --- | --- | --- |
| V1 | mittel | Bei 390 px waren nur Bezeichnung, Dienstleister und Objekt sichtbar; Laufzeit, Kündigungsfrist, berechnete Termine, Status und die Buttons Bearbeiten/Löschen lagen außerhalb des Bildschirms. | behoben: Kartenliste unter `sm` (`data-testid="service-contracts-cards"`) mit allen Feldern und Aktionen; Tabelle ab `sm`. |
| V2 | mittel | "1 Monate" (fehlende Einzahl) bei Kündigungsfrist 1 Monat oder 1 Tag. | behoben: ICU-Plural in `ServiceContracts.unit.*` (`{count, plural, one {Monat} other {Monate}}`), Auswahlfeld mit Mehrzahl. |
| V3 | mittel | Der Hinweis "Orientierung, zu prüfen" stand nur am spätesten Kündigungstermin, nicht am nächstmöglichen Vertragsende, das aus denselben Annahmen berechnet ist. Bei 1280 px drängten die Badges die Spalten Status und Aktionen aus dem sichtbaren Bereich. | behoben: Hinweiskasten über der Liste, Kennzeichnung an beiden berechneten Terminen (Tabelle als Textzeile, Karte als Badge), gesteuert über `orientation_only`; Laufzeit ohne Umbruch, Verlängerung als eigene Zeile. |
| V4 | niedrig | Keine Plausibilität im Formular: Ende vor Beginn oder Kündigung vor Beginn gingen an die API; keine Rückmeldung nach dem Speichern. | behoben: Prüfung im Formular ("Das Ende darf nicht vor dem Beginn liegen.", "Das Kündigungsdatum darf nicht vor dem Beginn liegen."), Meldung "Dienstleistervertrag gespeichert.", Hilfetexte zu Kündigungsfrist und "Gekündigt am". |
| V5 | niedrig | Spalte "Dienstleister" zeigt "Unbekannt", wenn der Vertragspartner nicht in den ersten 200 Kontakten mit Rolle `dienstleister` liegt oder die Rolle fehlt (`dienstleistervertraege/page.tsx`, `page_size: 200`). | offen: Anzeige des Namens aus dem Vertrag selbst (API `provider_name` in `service-contracts`) oder Nachladen je Vertrag; Seite liegt außerhalb des Auftrags, API parallel in Bearbeitung. |

### Kontaktliste (Filter, Massenaktionen, Paginierung)

| Nr. | Schwere | Befund | Status |
| --- | --- | --- | --- |
| K1 | niedrig | Paginierung: `GET /api/v1/contacts` liefert `total`, `page`, `page_size` im Body (`ContactPage`), keinen Header `X-Total-Count`. Die Seite rechnet daraus "Seite x von y", Zurück und Weiter; das ist korrekt. | unverändert gelassen (Vorgabe: Header nur nutzen, wenn vorhanden). |
| K2 | niedrig | Massenaktion "Schlagwort für markierte" (`BulkTagBar`) ist nur in der Tabellenansicht ab `sm` verfügbar; die Kartenliste unter `sm` hat keine Auswahl. Auf dem Telefon sind Massenaktionen damit nicht bedienbar. | offen: bewusst so gebaut (Kartenliste ohne Checkboxen); Entscheidung Betreiber, ob Massenaktionen mobil nötig sind. Komponente liegt in `components/workspace` (anderer Bereich). |
| K3 | niedrig | Filter (Suche, Art, Schlagwort, Rollen-Pills, gespeicherte Filter) funktionieren bei 1280 px und 390 px ohne horizontales Scrollen; Rollen-Pills tragen `aria-current`. | kein Handlungsbedarf |

## Geänderte Dateien

- `apps/web-crm/src/components/contacts/BankAccountApproval.tsx` (B2 bis B5, Prop `isPlatformAdmin`)
- `apps/web-crm/src/components/contacts/BankAccountApproval.test.tsx` (vier neue Tests)
- `apps/web-crm/src/components/contacts/CallsPanel.tsx` (C1 bis C3, Prop `canDismiss`)
- `apps/web-crm/src/components/contacts/CallsPanel.test.tsx` (ein neuer Test)
- `apps/web-crm/src/components/contracts/ServiceContracts.tsx` (V1 bis V4)
- `apps/web-crm/src/components/contracts/ServiceContracts.test.tsx` (zwei neue Tests, ein erweiterter)
- `apps/web-crm/src/app/(app)/kontakte/[id]/page.tsx` (B1, B6, Übergabe `isPlatformAdmin`, `canDismiss`)
- `apps/web-crm/messages/de.json`, `apps/web-crm/messages/en.json` (neue Schlüssel unter
  `Contacts.bankApproval`, `Calls`, `ServiceContracts`; `Contacts.bankApproval.rejectConfirm` entfernt)

## Tests

- `pnpm --filter @mhvp/web-crm test -- src/components/contacts src/components/contracts`: 7 Dateien,
  31 Tests bestanden (davon 7 neu). Der Formulartest in `ServiceContracts.test.tsx` hat wegen der
  Auslastung der Prüfumgebung ein Zeitlimit von 20 s.
- `tsc --noEmit`, `eslint` (Kontakt- und Vertragsbereich, `--max-warnings=0`),
  `scripts/check_i18n.py`: Ergebnis siehe Abschlussbericht des Agenten.
- Nicht ausgeführt: Playwright-E2E (`@backend`), da kein API-Backend verfügbar; die Screenshots
  entstanden gegen den gemockten Server.

## Offene Punkte

1. B7: Freigabeübersicht oder Kennzeichen "IBAN zur Freigabe" in der Kontaktliste (API-Erweiterung).
2. V5: Dienstleistername direkt aus dem Vertrag (API `provider_name`) statt Nachschlag über die ersten
   200 Dienstleister-Kontakte.
3. K2: Massenaktionen auf dem Telefon (Entscheidung Betreiber).
4. Die Begründung der Ablehnung wird von der API im Ereignisprotokoll gespeichert, aber nicht in
   `BankAccountOut` zurückgegeben; am Kontakt ist sie nach dem Neuladen nicht sichtbar. Anzeige über
   das Ereignisprotokoll oder ein Feld `decision_reason` wäre eine API-Erweiterung.
