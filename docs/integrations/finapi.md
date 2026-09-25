# finAPI Access Integration (M11-finapi)

Binding interface document for `apps/api/src/mhvp/banking/finapi.py`
(`mhvp.banking.finapi.FinApiClient`). The client calls only the endpoints listed here as
verified; every field or endpoint marked "zu prüfen" is not called and raises
`FinApiNotVerifiedError` (`MHVP-BANK-0003`) instead of guessing a path or a field name
(master prompt section 3, rule 0.1.3).

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
| User token | `POST /oauth/token` | `grant_type=password`, plus `username`/`password` of a finAPI user identity. **Not used by this client**: this stage does not create finAPI user identities interactively; kept here only because the same endpoint is documented for both flows. |
| Create user (technical identity) | `POST /users` | Field `isAutoUpdateEnabled`: set to `false` to keep the provider's own automatic update off (master prompt section 2). Not called automatically yet; see "zu prüfen" below for the exact multi-user/mandator model. |
| Start WebForm bank connection import | `POST /api/webForms/bankConnectionImport` | Response fields verified: `id` (WebForm id), `url` (redirect URL), `status`, `payload.bankConnectionId`. Optional request field used here: `accountTypeIds` (restricts requested account types); exact allowed values are "zu prüfen" (see below), so the client only forwards a list the caller already validated elsewhere and never invents one. |
| WebForm status | `GET /api/webForms/{id}` | Same response fields as above. |
| Bank connection status | `GET /bankConnections/{id}` | Read only in this client. |
| List accounts | `GET /accounts` | Filter parameters documented: `accountTypes`, `id`. This client also passes `bankConnectionId`, which matches the documented navigation ("Konten auflisten" scoped to a connection) but the exact filter key is "zu prüfen" (see below); it is defensive, a wrong key only means finAPI ignores it and returns more accounts, so results are still filtered client-side by `bankConnectionId` before use. |
| List transactions | `GET /transactions` | Basic pagination assumed (`page`, `perPage`); exact field names, sort order and booked/pending semantics are "zu prüfen" (see below). |

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
- Rate limits, documented retry rules, and per-account feature flags (Q8): not modelled;
  server errors surface as `MHVP-BANK-0002` without an automatic retry loop.

## Not implemented in this stage

- Payments, direct debits, payment approval (out of scope per master prompt section 2).
- Automatic/scheduled fetch. `FinApiConnection.auto_update_enabled` is always created `false`
  and there is no Celery beat entry for finAPI; `banking.finapi_fetch` only runs when a user
  click enqueues a `BankSyncRun` (`mhvp.banking.routers.fetch_finapi_transactions`).
- finAPI user identity creation via `POST /users` (see table above); the current design uses
  only the client-credentials token. Whether a per-tenant finAPI **user** (as opposed to just
  an application) is required for the WebForm 2.0 flow is open (`docs/OPEN_QUESTIONS.md`
  M11-40), and no user identity is invented to work around that.

## Local development and tests

`tests/banking/test_finapi.py` uses `httpx.MockTransport` behind `FinApiClient` and never
claims a live connection. Without a `FinApiTenantConfig` row, `GET /banking/finapi/config`
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
(per bank, every assigned account) take an optional `{since, until}` body. Neither bound is
sent to finAPI: `/transactions` documents no confirmed date filter (see "Zu prüfen"), so the
client fetches every page finAPI returns and only *keeps* rows inside the requested range
client side. **History depth is wie vom Anbieter geliefert**: this integration does not know,
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
