# Banking über finAPI Access (M31, erste Ausbaustufe)

Stand: 25.09.2026. Rein lesende Bankanbindung über finAPI Access mit WebForm 2.0. Keine
Zahlungsauslösung, keine zeitgesteuerten Bankabrufe, keine Verarbeitung von Bank-PIN oder TAN in
dieser Software: die Bankanmeldung geschieht ausschließlich im WebForm des Providers.

## Was implementiert ist

- Provider-Abstraktion `mhvp.banking.finapi` (Protocol `BankingAggregator`, Implementierung
  `FinApiClient`) mit den dokumentierten Endpunkten: OAuth (`/oauth/token`, client_credentials
  und password), Nutzeranlage `POST /api/v1/users` mit `isAutoUpdateEnabled=false`,
  WebForm 2.0 `POST /api/webForms/bankConnectionImport` und `bankConnectionUpdate`,
  `GET /api/webForms/{id}`, Update-Tasks `POST /api/tasks/backgroundUpdate` und
  `GET /api/tasks/{id}`, Daten `GET /api/v1/accounts` und `GET /api/v1/transactions`
  (Paging `page`/`perPage`, `minBankBookingDate`), `DELETE /api/v1/bankConnections/{id}`.
- Je Bankverbindung eine eigene Provider-Identität (verschlüsselt gespeichert), gebunden an den
  SaaS-Mandanten und einen dokumentierten Berechtigungskontext (`authorization_context`,
  Pflichtfeld beim Verbinden). Keine globale Banking-Identität für alle Kunden.
- Dauerhaftes Datenmodell: `bank_account_link` (Quellenzuordnung externes Konto -> internes
  `property_bank_account`, IBAN verschlüsselt + Fingerprint, Zeitstempel getrennt: letzter
  Versuch, letzte Bankaktualisierung, zuletzt übernommen), `bank_balance`
  (Saldo-Schnappschüsse, gebucht und verfügbar getrennt, bankseitiger Referenzzeitpunkt nur
  wenn geliefert), Abruffelder auf `bank_sync_run` (Auslöser, Bediener, Zustand,
  WebForm/Task-Referenzen, Ergebnis je Konto). RLS auf allen neuen Tabellen (ADR 0002).
- Abläufe: Verbinden -> WebForm -> serverseitige Bestätigung (ein Redirect oder Callback ist nur
  ein Hinweis, das Ergebnis wird immer mit eigenen Zugangsdaten gegen den Provider geprüft) ->
  Konten auswählen und zuordnen -> Abruf nur auf Nutzerklick (Celery-Queue `bank`, ein aktiver
  Lauf je Verbindung, Doppelklick liefert denselben Lauf) -> Update-Task verfolgen ->
  `WEB_FORM_REQUIRED` wechselt auf das Update-WebForm, derselbe Lauf wird nach der Freigabe
  fortgesetzt -> Import nur gebuchter Umsätze mit Überlappungsfenster und idempotentem Ingest
  (Identität = Provider-Umsatz-ID je Konto; reiner Inhaltsgleichstand nur als Prüffall).
- Übergabe an die Buchhaltung: es entstehen ausschließlich `BankTransaction` im Status `new`;
  kein automatischer Buchungssatz. Nicht zugeordnete Konten werden protokolliert und gelangen
  nicht in die Buchhaltung. Ein Zuordnungswechsel verschiebt keine vorhandenen Umsätze.
- Trennen: Verbindung wird zuerst lokal gesperrt, dann die Provider-Verbindung im verfügbaren
  Umfang gelöscht; Fehler bleiben sichtbar. Konten, Umsätze und Protokolle bleiben erhalten.
  Ein bankseitiger Consent-Widerruf wird nicht behauptet.
- Nächtliche Dateisynchronisation (`sync_all`) lässt finAPI-Verbindungen ausdrücklich aus:
  keine zeitgesteuerten Bankabrufe.

## Konfiguration (Projektkonfiguration, keine Provider-Standardnamen)

| Variable | Bedeutung |
| --- | --- |
| `MHVP_BANKING_FINAPI_BASE_URL` | Basis-URL der für diesen Client freigeschalteten Umgebung (Sandbox oder Produktion; niemals mischen). |
| `MHVP_BANKING_FINAPI_CLIENT_ID` / `MHVP_BANKING_FINAPI_CLIENT_SECRET` | Client-Zugangsdaten aus dem finAPI-Vertrag. |
| `MHVP_BANKING_FINAPI_CALLBACK_BASE_URL` | Öffentliche API-Basis für den WebForm-Callback (`/api/v1/banking/finapi/callback/...`); optional, der Callback ist nur ein Hinweis. |
| `MHVP_BANKING_FETCH_OVERLAP_DAYS` | Überlappungsfenster des Umsatzabrufs in Tagen (Standard 10). |

Sind die drei ersten Variablen nicht gesetzt, meldet die Oberfläche „Bankanbindung noch nicht
eingerichtet"; es entstehen keine Demo-Daten.

## Ausgeführte Tests und ihre Grenzen

Ausgeführt (lokal, 25.09.2026): `tests/integration/test_m31_banking_finapi.py`, 10 Tests grün,
gegen echtes PostgreSQL mit RLS und einen stateful Fake der oben genannten finAPI-Endpunkte
(httpx MockTransport). Abgedeckt: Verbinden/Bestätigen/Zuordnen mit Persistenz, Identität ohne
automatische Abrufe, Abruf nur gebuchter Umsätze, Wiederholung ohne Duplikate, zwei echte
gleichhohe Zahlungen bleiben zwei, Vormerkungen übersprungen, `WEB_FORM_REQUIRED` mit
Fortsetzung desselben Laufs, Doppelklick liefert denselben Lauf, Abbruch/Ablauf zerstört keine
Verknüpfung, Teilfehler ergibt `partial`, Wiederanbindung mit neuen Provider-IDs über
IBAN-Fingerprint, Fremdmandant sieht nichts, manipulierter Callback-Token wird ignoriert,
unkonfiguriert ergibt 409, Trennen stoppt Abrufe und erhält Historie, kein Buchungssatz.

Nicht ausgeführt und durch die Mock-Tests nicht bewiesen: echte Provider-Sandbox, reale
Banktests, Lasttests, Produktivfreigabe. Eine bestandene Mock-Testreihe beweist keine
funktionierende Bankanbindung.

## Vor Produktivstart zu klären (nichts davon ist erfüllt, solange es hier steht)

1. finAPI-Vertrag und Zugangsdaten für die Zielumgebung; WebForm-2.0-Freischaltung für den
   konkreten Client; aktivierte API-Version des Clients gegen die implementierten Endpunkte
   prüfen (geprüfter Dokumentationsstand: 25.09.2026).
2. Q8: die vom Provider für nutzerveranlasste Abrufe geforderten Angaben (tatsächliche
   Nutzer-IP, Geräte-/Browserinformationen) sind in dieser Ausbaustufe noch nicht an den
   Provider durchgereicht; Umfang und Pflicht mit der aktuellen Provider-Dokumentation und dem
   Anbieter klären und vor Produktivstart nachrüsten.
3. Q6: Mehrbenutzer- und Vertretungsmodell (Vollmachts-/WEG-Konten, Verwalter als Bevollmächtigter)
   mit dem Anbieter abstimmen; ein finAPI-Mandator ist nicht ungeprüft ein SaaS-Mandant.
4. Rechtlicher Rahmen: Kontoinformationsdienste sind reguliert (§ 34 ZAG); ob die eigene
   Nutzung unter die Erlaubnis des Providers fällt, ist mit Provider und Rechtsberatung zu
   klären. Diese Software behauptet keine eigene Erlaubnis.
5. Von der Bank tatsächlich gelieferte Historie dokumentieren; es wird keine feste Rückschau
   versprochen.
