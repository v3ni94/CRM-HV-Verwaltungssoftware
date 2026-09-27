# finAPI Access Integration (M11-finapi)

Binding interface document for `apps/api/src/mhvp/banking/finapi.py`
(`mhvp.banking.finapi.FinApiClient`). The client calls only the endpoints listed here as
verified; every field or endpoint marked "zu prüfen" is not called and raises
`FinApiNotVerifiedError` (`MHVP-BANK-0003`) instead of guessing a path or a field name
(master prompt section 3, rule 0.1.3).

## Betreiberentscheidung 26.09.2026 (M11-01)

Der Aggregator finAPI ist die primäre Bankanbindung und wird zuerst umgesetzt. Der
Datei-Import (CAMT.053, MT940) bleibt bestehen. EBICS folgt später (V2, Bankverträge).
Umfang dieser Stufe: ausschließlich Konten- und Umsatzabruf. Keine Zahlungsauslösung, Gate G2
bleibt geschlossen; Zahlungsfreigaben laufen unverändert über `mhvp.banking.payments` und
sind ohne G2 gesperrt.

### Voraussetzungen

- finAPI-Vertrag (Access, WebForm 2.0) mit aktivierter Client-ID und Client-Secret je
  Mandant; Eintrag unter Einstellungen, Bank (`PUT /banking/finapi/config`), verschlüsselt
  gespeichert (`FinApiTenantConfig`, Feldverschlüsselung wie alle Verbindungen).
- Auftragsverarbeitungsvertrag (AVV) mit finAPI und Prüfung § 34 ZAG für dieses SaaS-Modell:
  offen, siehe `docs/OPEN_QUESTIONS.md` M11-40. Ohne AVV kein Produktivbetrieb mit echten
  Kontodaten.
- Basis-URL je Rechenzentrum: leer lassen, dann gilt der Standard aus den Einstellungen
  (`MHVP_FINAPI_BASE_URL_SANDBOX`, Standard `https://sandbox.finapi.io`;
  `MHVP_FINAPI_BASE_URL_LIVE`, Standard `https://live.finapi.io`, beide [laut finAPI-Doku]).
  Nur `https://` wird angenommen. Das Sandbox-Kennzeichen (`sandbox`) wählt den Standard und
  wird am Konfigurationsereignis protokolliert.
- Keine Bankzugangsdaten im CRM: PIN und TAN werden ausschließlich im finAPI-WebForm
  eingegeben (`docs/rules/M11-04-no-credentials-in-crm.md`). Gespeichert werden nur
  WebForm-ID, WebForm-URL und WebForm-Status.

### Ablauf (Token, WebForm, Abruf)

1. Client-Token: `POST /oauth/token` mit `grant_type=client_credentials` (Client-ID und
   Client-Secret des Mandanten). Wird nur für die Anlage der technischen finAPI-Benutzer
   verwendet und im Prozess zwischengespeichert (Ablauf laut `expires_in` minus 30 Sekunden).
2. Benutzer je Bankverbindung: beim ersten „Bank verbinden“ legt `POST /users` mit
   `isAutoUpdateEnabled=false` einen technischen finAPI-Benutzer an (kein Auto-Update durch
   den Anbieter). Die von finAPI erzeugten Werte `id` und `password` werden verschlüsselt an
   der Verbindung gespeichert (`FinApiConnection.finapi_user_id`, `finapi_user_password`,
   Migration 0141). Sie sind Anbieterzugangsdaten, keine Bankzugangsdaten.
3. Benutzer-Token: `POST /oauth/token` mit `grant_type=password` und diesen Werten. Alle
   Datenaufrufe einer Verbindung (WebForm, Bankverbindung, Konten, Umsätze) laufen unter dem
   Benutzer-Token; das Client-Token allein liest keine Kontodaten.
4. WebForm-Import: `POST /api/webForms/bankConnectionImport`, der Browser öffnet die
   gelieferte URL in einem neuen Tab. `POST /banking/finapi/connections/{id}/check` prüft
   danach WebForm-Status, Bankverbindung und Konten serverseitig neu; die Rückkehr des
   Browsers allein gilt nie als Erfolg.
5. Kontenliste: `GET /accounts` je Bankverbindung; Konten bleiben bis zur Zuordnung an ein
   `property_bank_account` (Rechtsträger, Objekt) unzugeordnet und für Nutzer ohne
   `banking:approve` unsichtbar.
6. Umsatzabruf inkrementell: `GET /transactions` je Konto mit `accountIds`, `page`,
   `perPage` und den Datumsgrenzen `minBankBookingDate`/`maxBankBookingDate` [laut
   finAPI-Doku, Parameternamen gegen die aktivierte API-Version zu prüfen, M11-41]. Ohne
   Angabe eines Zeitraums beginnt der Abruf am Cursor des Kontos
   (`FinApiAccountLink.last_synced_booking_date`, neuestes importiertes Buchungsdatum)
   abzüglich einer Überlappung von drei Tagen (`tasks.SYNC_OVERLAP_DAYS`), weil Banken
   Umsätze nachträglich mit früherem Buchungsdatum liefern können. Die Datumsgrenze wird auf
   die gelieferten Zeilen erneut angewendet; ein Anbieter, der den Parameter ignoriert, liefert
   nur mehr Zeilen. Die Seitenzahl wird aus `paging.pageCount` gelesen, sonst gilt eine volle
   Seite als „weitere möglich“.
7. Idempotenter Upsert: jede Zeile wird mit `bank_reference = "finapi:<id>"` in
   `bank_transaction` abgelegt (`services.import_finapi_transactions`, Regel D05: Referenz
   zuerst, Inhaltshash als zweite Stufe). Eine erneut gelieferte Zeile wird als Duplikat
   gezählt, nie überschrieben; gebuchte Umsätze bleiben unverändert (Regel 0.1.7). Beträge
   werden als `Decimal` aus dem gelieferten Text gelesen und als `NUMERIC(14,2)` gespeichert,
   nie als Float. Nach erfolgreichem Lauf rückt der Cursor auf das neueste Buchungsdatum und
   die zugehörige Transaktions-ID (`last_synced_transaction_id`).
8. Hintergrundjob: `mhvp.banking.finapi_scheduled_fetch` (Celery beat, täglich 06:30) stellt
   für jeden Mandanten mit `auto_fetch_enabled=true` je zugeordnetem Konto einen
   `BankSyncRun` ein und führt denselben Abruf wie der Klick aus (`mhvp.banking.finapi_fetch`).
   Standard aus, keine globale Übersteuerung (ADR 0003).

### Fehlerzuordnung (ADR 0004, `mhvp.core.problems`)

| Situation | Code | HTTP | Verhalten |
| --- | --- | --- | --- |
| Keine Konfiguration für den Mandanten | `MHVP-BANK-0001` | 502 | Aktion abgelehnt, UI zeigt „nicht eingerichtet“ |
| Anbieter nicht erreichbar, Transportfehler, 5xx, sonstige 4xx | `MHVP-BANK-0002` | 503 | Lauf `failed`, Cursor unverändert |
| Endpunkt als „zu prüfen“ markiert | `MHVP-BANK-0003` | 501 | wird nicht aufgerufen |
| Falscher Zustand der Verbindung | `MHVP-BANK-0004` | 409 | Aktion abgelehnt |
| 401 oder 403 (Client- oder Benutzer-Token abgelehnt) | `MHVP-BANK-0005` | 502 | Lauf `failed`, `last_error` an der Verbindung, Zugangsdaten prüfen |
| 429 Ratenlimit | `MHVP-BANK-0006` | 503 | Lauf `failed`, `Retry-After` als Erweiterung, keine automatische Wiederholung; der nächste geplante oder manuelle Abruf setzt am Cursor wieder auf |

Der Antworttext des Anbieters wird nur als Entwicklerhinweis (gekürzt) gehalten und nie als
Nutzertext angezeigt.

### Grenzen

- Nur lesend. Keine Zahlungen, keine Lastschriften, kein Zahlungsfreigabefluss über finAPI.
- Kein Callback oder Webhook; Status wird serverseitig mit eigenen Zugangsdaten abgefragt.
- Historientiefe wie vom Anbieter und der Bank geliefert (M11-46); nichts wird ergänzt.
- Feldnamen für Datumsgrenzen, Paging und Salden sind gegen die aktivierte API-Version zu
  prüfen (M11-41). Bis dahin gelten sie als [laut finAPI-Doku] und werden defensiv gelesen.
- Trennen und Aktualisieren einer Bankverbindung anbieterseitig bleiben unverifiziert
  (M11-42, M11-43); Erneuerung nur über ein neues WebForm.
- Tests laufen ausschließlich gegen `httpx.MockTransport` (`tests/unit/test_finapi_client.py`,
  `tests/integration/test_m11_finapi.py`); ein Sandbox-Test mit echten Zugangsdaten steht aus.

### Offene Punkte

- finAPI-Vertrag, Lizenzumfang und AVV (M11-40), Prüfung § 34 ZAG.
- Aktivierte API-Version und Feldschema (M11-41), Ratenlimits laut Vertrag (M11-45).
- Mandator-Modell (M11-44): `mandator_id` bleibt nur ein Hinweis-Header.
- Sandbox-Abnahme mit echten Zugangsdaten durch den Betreiber, danach Live-Umschaltung je
  Mandant (`sandbox=false`); G2 bleibt unabhängig davon geschlossen.

## Status

- API: finAPI Access API, WebForm 2.0 integration model for customers without their own AIS
  registration (unlicensed/WebForm model).
- Retrieval date of the pages actually fetched for this document: **25.09.2026**.
- Scope of this stage: **read only** (bank connection, accounts, balances, transactions).
  No payment initiation, no automatic scheduled fetch, provider auto update disabled.
- Verified against: `documentation.finapi.io` pages listed under "Sources" below, fetched on
  25.09.2026. Not verified against a concrete client's activated API version or a signed
  finAPI contract (open, see `docs/OPEN_QUESTIONS.md` M11-40 to M11-45).

## Verified endpoints

| Purpose | Method & path | Notes |
| --- | --- | --- |
| Client token (application) | `POST /oauth/token` | `grant_type=client_credentials`, `client_id`, `client_secret`; bearer token, `expires_in` seconds (documented example: 3599). |
| User token | `POST /oauth/token` | `grant_type=password`, plus `username`/`password` of the finAPI user identity of one bank connection (`FinApiClient._user_token_value`). Used for every data call of a connection since 26.09.2026 (see "Ablauf" above). |
| Create user (technical identity) | `POST /users` | Called once per bank connection with the client token (`FinApiClient.create_user`), `isAutoUpdateEnabled=false` (master prompt section 2); `id` and `password` from the response are stored encrypted on `FinApiConnection`. The multi-user/mandator model stays "zu prüfen" (M11-44). |
| Start WebForm bank connection import | `POST /api/webForms/bankConnectionImport` | Response fields verified: `id` (WebForm id), `url` (redirect URL), `status`, `payload.bankConnectionId`. Optional request field used here: `accountTypeIds` (restricts requested account types); exact allowed values are "zu prüfen" (see below), so the client only forwards a list the caller already validated elsewhere and never invents one. |
| WebForm status | `GET /api/webForms/{id}` | Same response fields as above. |
| Bank connection status | `GET /bankConnections/{id}` | Read only in this client. |
| List accounts | `GET /accounts` | Filter parameters documented: `accountTypes`, `id`. This client also passes `bankConnectionId`, which matches the documented navigation ("Konten auflisten" scoped to a connection) but the exact filter key is "zu prüfen" (see below); it is defensive, a wrong key only means finAPI ignores it and returns more accounts, so results are still filtered client-side by `bankConnectionId` before use. |
| List transactions | `GET /transactions` | Pagination `page`, `perPage`, envelope `paging.pageCount` read defensively; date bounds `minBankBookingDate`/`maxBankBookingDate` sent for the incremental sync [laut finAPI-Doku, M11-41] and applied again client side; sort order and booked/pending semantics are "zu prüfen" (see below). |

## Zu prüfen (not verified, not called without confirmation)

The following are used nowhere in `finapi.py` beyond a placeholder that raises
`FinApiNotVerifiedError`, or are read defensively (missing key becomes `None`) rather than
asserted:

- Exact JSON field names for account IBAN, balance (booked vs. available), balance
  reference date, and account type/owner strings (`_account_from_json` reads several
  candidate keys and never asserts one is required).
- Exact JSON field names and semantics for a transaction's booked/pending status, the
  distinction between `bankBookingDate` and value date, reversal (`Rücklastschrift`) and true
  cancellation markers, and the pagination envelope (`_transaction_from_json` and
  `list_transactions` are similarly defensive).
- The concrete endpoint, method and body for **updating** an existing bank connection
  ("Update a Bank Connection – for Web Form 2.0 customers"): the navigation names this
  process, but the fetched pages did not return a confirmed method/path/body, so
  `FinApiClient.trigger_update` raises instead of guessing (`MHVP-BANK-0003`). Update is
  effectively only reachable today through a fresh `bankConnectionImport` WebForm
  (re-authorization), which **is** verified.
- The concrete endpoint for deleting/deactivating a bank connection on the provider side.
  `FinApiClient.disconnect` raises; the application's "Trennen" action only removes the
  local link and records that the provider side is unconfirmed (`docs` section "Trennen"
  below and `mhvp.banking.routers.disconnect_finapi_connection`).
- Callback/webhook payload shape and signature scheme (Q10). Not implemented in this stage;
  the application only re-checks status by polling with its own credentials, never trusting
  a callback body alone (master prompt section 8).
- The finAPI "application"/"mandator" concept for multi-user or multi-mandator setups (Q6):
  `FinApiTenantConfig.mandator_id` is stored and sent as an informational header only
  (`X-MHVP-Mandator-Hint`); it is **not** asserted to correctly scope a SaaS tenant to a
  finAPI mandator without confirmation from finAPI support (see `docs/OPEN_QUESTIONS.md`).
- Rate limits, documented retry rules, and per-account feature flags (Q8): contractual
  limits not modelled; HTTP 429 surfaces as `MHVP-BANK-0006` (with `Retry-After`), 401/403
  as `MHVP-BANK-0005`, other errors as `MHVP-BANK-0002`, all without an automatic retry loop.

## Not implemented in this stage

- Payments, direct debits, payment approval (out of scope per master prompt section 2).
- Automatic/scheduled fetch. `FinApiConnection.auto_update_enabled` is always created `false`
  and there is no Celery beat entry for finAPI; `banking.finapi_fetch` only runs when a user
  click enqueues a `BankSyncRun` (`mhvp.banking.routers.fetch_finapi_transactions`).
- Payment related finAPI products of any kind (G2 closed).

## Local development and tests

`tests/unit/test_finapi_client.py`, `tests/unit/test_banking_connectors.py` and
`tests/integration/test_m11_finapi.py` use `httpx.MockTransport` behind `FinApiClient` and
never claim a live connection. Without a `FinApiTenantConfig` row, `GET /banking/finapi/config`
answers `{"configured": false}` and the UI shows "Bankanbindung noch nicht eingerichtet"
(no silent switch to demo data, master prompt section 13).

## Rebuild (M11-finapi Stages 1 to 6, operator decision 25.09.2026)

PSD2/XS2A via finAPI Access is the primary path for unlimited banks going forward, next to the
existing file (CSV/CAMT) upload; HBCI/FinTS is explicitly not built now, only the seam for it
(`mhvp.banking.connectors.BankConnector`, `mhvp.banking.finapi.FinApiConnector`).

### WebForm flow (as implemented)

1. `POST /banking/finapi/connections` (`bank_name` free text, descriptive only) calls
   `create_bank_connection_import_web_form` and returns a `web_form_url`. The bank itself is
   **not** searched or selected by this backend beforehand: no verified bank-search endpoint
   exists for the WebForm 2.0 model (see "Zu prüfen" above), so bank selection by IBAN, BIC or
   name happens inside the WebForm the browser is redirected to.
2. The CRM opens `web_form_url` in a new tab (`window.open(..., "_blank")`); this keeps the
   original tab's session cookies (SameSite=Strict) without needing the same-site return page.
   A top-level, full-navigation return flow through `apps/web-crm/src/app/api/session/return`
   is available and used elsewhere for OAuth-style redirects, but is not wired to finAPI here
   because no verified callback/redirect URL parameter exists for the WebForm creation call
   (see "Zu prüfen"); wiring it later needs that parameter confirmed first, not guessed.
3. `POST /banking/finapi/connections/{id}/check` re-reads the WebForm and, once finished, the
   bank connection and its accounts with the tenant's own credentials (never trusts the browser
   return alone). Accounts appear unassigned until a person assigns each one to a
   `property_bank_account` (legal entity/ledger and, through that account, a property).

### Consent renewal ("Erneut freigeben")

`POST /banking/finapi/connections/{id}/reauthorize` opens a fresh WebForm on the same
connection (the only reachable re-authorization path; "Update a Bank Connection" is
unverified, see above) and sets the connection to `update_required` until `check` confirms it
again. `FinApiConnection.consent_valid_until` is stored but not yet populated by
`complete_connection`/`check`: no verified field carries a consent expiry date from finAPI
(see "Zu prüfen"); the CRM only shows an expiry once that field is confirmed. The daily
`banking.sync_all` job's consent-expiry reminder still runs against
`BankConnection.consent_valid_until` for whichever connector sets it.

### Transactions, date range and history depth

`POST /banking/finapi/accounts/{id}/fetch` and `POST /banking/finapi/connections/{id}/fetch`
(per bank, every assigned account) take an optional `{since, until}` body. Since 26.09.2026
the bounds are sent as booking date parameters [laut finAPI-Doku, M11-41] and applied again
on the returned rows; without a body the fetch is incremental from the account's cursor (see
"Ablauf" above). **History depth is wie vom Anbieter geliefert**: this integration does not know,
and does not claim, how far back a given bank or a given finAPI contract tier actually
delivers transactions; that varies per bank and is not modelled or promised anywhere in this
codebase (open point, see `docs/OPEN_QUESTIONS.md`).

### Scheduled fetch (opt-in, default off)

`FinApiTenantConfig.auto_fetch_enabled` (default `false`) gates the Celery beat job
`mhvp.banking.finapi_scheduled_fetch` (`apps/api/src/mhvp/worker.py`, daily 06:30). A tenant
that has not explicitly opted in never has anything queued by it; a manual click is always
independent of this flag. Idempotent by provider transaction id (`bank_reference =
"finapi:<id>"`), same as every other fetch path (D05).

## Sources

Official documentation, fetched 25.09.2026 for this document:

- WebForm and unregulated integration customers: https://documentation.finapi.io/webform
- Licensed vs. unlicensed: https://documentation.finapi.io/access/licensed-vs-unlicensed
- User identity and automatic updates:
  https://documentation.finapi.io/access/authorization-and-creation-of-a-user-identity
- API version binding:
  https://documentation.finapi.io/access/upgrading-to-a-new-api-version
- WebForm product/UI version:
  https://documentation.finapi.io/webform/web-form-documentation-2-0-2-1
- Application management / mandator:
  https://documentation.finapi.io/access/application-management
- Import with WebForm 2.0:
  https://documentation.finapi.io/access/import-a-new-bank-connection-with-web-form-2-0-rec
- Update with WebForm 2.0 (navigation only, endpoint not confirmed):
  https://documentation.finapi.io/access/update-a-bank-connection-for-web-form-2-0-customer
- Post-processing of import/update:
  https://documentation.finapi.io/access/post-processing-of-bank-account-import-update
- Callbacks/redirects: https://documentation.finapi.io/webform/callbacks-redirects
- API reference: https://docs.finapi.io/
- § 34 ZAG (account information services):
  https://www.gesetze-im-internet.de/zag_2018/__34.html

These sources establish provider behaviour and the regulatory hint; they are not proof that
this project already holds a finAPI contract, technical activation, or a completed § 34 ZAG /
BaFin assessment for this SaaS model (see `docs/OPEN_QUESTIONS.md` M11-40 to M11-45).
