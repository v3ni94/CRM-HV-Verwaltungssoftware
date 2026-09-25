# M11-finapi: read only finAPI Access integration (plan and result)

Status: implemented, 25.09.2026. Source: operator's supplementary banking master prompt
(`/root/.claude/uploads/.../MH-Verwaltungsplattform_Banking_SaaS_Prompt.md`), binding for this
task; `docs/MASTER-PROMPT.md` sections 6.4, 6.9.7, 8, 18 (M11); builds on `docs/plans/M11.md`
without changing file import, matching or payment orders.

## Bestandsaufnahme (section 1 of the banking master prompt)

- `mhvp.banking.connectors.BankConnector` already defines the exchangeable interface (list
  accounts, fetch transactions); `UnconfiguredConnector` reports "not configured" for every
  connector besides file import. Extended, not replaced: `FinApiClient`
  (`mhvp.banking.finapi`) implements the same shape plus the WebForm specific calls the
  interface does not cover (create/poll WebForm, get bank connection).
- `BankConnection`, `BankSyncRun`, `BankStatement`, `BankTransaction` already exist
  (migration 0011) with the dedup rule required by section 9 of the prompt (bank reference
  primary key per account, content hash a duplicate hint only, D05). Reused as is;
  `mhvp.banking.services.import_finapi_transactions` mirrors `import_file`'s dedup instead of
  duplicating a second rule.
- `ConnectionStatus` extended with `web_form_pending` and `update_required` (migration 0050);
  `active`/`error`/`disabled` reused for connected/error/disconnected, `not_configured` for
  the pre-WebForm "created" state (section 8 of the prompt: internal state names only, no
  claimed finAPI enum).
- No existing model for provider credentials per tenant, external account references, or
  WebForm/connection tracking: added `finapi_tenant_config`, `finapi_connection`,
  `finapi_account_link` (section 5 of the prompt).

## Decisions

- One companion row per `bank_connection` (`finapi_connection`) instead of overloading
  `BankConnection` with finAPI only columns, so the generic table stays connector agnostic
  (EBICS/GoCardless can get their own companion later, per `mhvp.banking.connectors`).
- `finapi_account_link` is the "Konto-Quellenzuordnung" of section 5: external
  `finapi_account_id` to at most one `property_bank_account_id`; unassigned rows stay
  invisible to everyone without `banking:approve` or `tenant_settings:update` (section 4).
- New permission `banking:approve` (connect, assign, re-authorize, disconnect, see unassigned
  accounts); plain `accounting:read`/`update` still cover listing and manual transaction
  fetch, matching the existing accounting-centric authorization of `mhvp.banking.routers`.
- Provider credentials: `finapi_tenant_config`, one row per tenant, `client_id`/`client_secret`
  via `EncryptedText` (same primitive as `BankConnection.credentials`); edited under
  `PUT /banking/finapi/config` (`tenant_settings:update`), never returned in plain text.
- WebForm creation happens synchronously in the request (finAPI's own documented endpoint is
  a fast, synchronous call); the transaction fetch after a click is asynchronous via the
  existing Celery worker (`mhvp.banking.tasks.finapi_fetch`), started only from
  `POST /banking/finapi/accounts/{id}/fetch`. No Celery beat schedule was added for finAPI;
  `mhvp.banking.tasks.sync_all` (file import connectors + consent reminder) is unchanged.
- Browser return from the WebForm is never trusted: `POST /connections/{id}/check` re-reads
  WebForm and bank connection status from finAPI with the tenant's stored credentials before
  any account or balance is written (section 6, 8 of the prompt).
- Disconnect blocks local use immediately (`BankConnection.status = disabled`) but does not
  claim the bank-side consent was revoked, because the provider-side delete/deactivate
  endpoint is unverified (`docs/integrations/finapi.md`, "zu prüfen"); this is recorded on the
  connection (`last_error`) and surfaced in the UI rather than hidden.
- No endpoint or field beyond what `docs/integrations/finapi.md` lists as verified is called;
  unverified ones raise `MHVP-BANK-0003` (update, disconnect) instead of guessing.

## Result

Files: `apps/api/src/mhvp/banking/finapi.py` (client), `models.py` (three new tables, two new
`ConnectionStatus` values), `routers.py` (`/banking/finapi/...`), `tasks.py`
(`banking.finapi_fetch`), `services.py` (`import_finapi_transactions`),
`apps/api/alembic/versions/0050_finapi_banking.py`, `mhvp.core.problems`
(`MHVP-BANK-0001..0004`), `mhvp.core.auth.permissions` (`banking` resource, `banking:approve`).
Web: `apps/web-crm/src/components/banking/FinApiConnections.tsx` (section "Bankverbindungen"
on `/bank`), settings card in `apps/web-crm/src/app/(app)/einstellungen/page.tsx`.

Tests: `apps/api/tests/banking/test_finapi.py` (fake provider via `httpx.MockTransport`;
acceptance cases 1 (multiple accounts, assignment), 3 to 6 (real update trigger via the queued
`BankSyncRun`/Celery call, WEB_FORM_REQUIRED handling, expired/aborted WebForm keeps the link),
7 (double click reuses the queued run instead of a second provider call is **not** fully
covered — see "Open points"), 8 (partial account failure visible), 9 (failed fetch keeps the
last good data), 10/11 (dedup, two real 700 EUR payments stay two, reusing the existing D05
rule), 15 (authorization: `banking:approve` required for unassigned accounts and connect/
disconnect, tenant separation), 19 (no config -> "not configured", never demo data).

Ruff, mypy and the targeted pytest run are reported in the final message; tests not executed
are named explicitly there (no live finAPI sandbox or bank in this environment).

## Open points (original stage)

M11-40 to M11-45 in `docs/OPEN_QUESTIONS.md` (finAPI contract/licensing, § 34 ZAG assessment,
mandator model, update endpoint confirmation, callback signature, rate limits). Gate: G2 is not
affected, this stage is read only; G1 (productive bookkeeping of the resulting transactions)
already gates on the existing accounting release, unchanged here.

## Umbau (Stages 1 to 6, operator decision 25.09.2026)

PSD2/XS2A via the finAPI aggregator becomes the primary path for unlimited banks, next to the
existing file upload; HBCI/FinTS is explicitly deferred, only the seam for a later adapter is
built. Six stages, each gated (ruff, mypy, alembic, targeted pytest; tsc, eslint, vitest for the
web app) before the next started:

- **Stage 1 -- provider abstraction.** `mhvp.banking.connectors.BankConnector` extended with
  `search_bank`, `start_connection`, `complete_connection`, `refresh_consent` (plus the
  existing `list_accounts`/`fetch_transactions`); `FinApiConnector` implements it on top of the
  unchanged `FinApiClient`; a new `FileConnector` puts the CSV/CAMT path on the same seam
  without changing its behaviour; `UnconfiguredConnector` (FinTS/EBICS placeholder) implements
  it too. No migration. Tests: `apps/api/tests/unit/test_banking_connectors.py`.
- **Stage 2 -- onboarding, consent, transactions.** `FinApiTenantConfig.auto_fetch_enabled`
  (default off, migration `0059`); `/banking/finapi/accounts/{id}/fetch` and the new
  `/banking/finapi/connections/{id}/fetch` (per bank) take an optional date range; new Celery
  beat task `mhvp.banking.finapi_scheduled_fetch`, opt-in per tenant. Fixed a real regression in
  `mhvp.banking.tasks.sync_tenant`: it routed every non-file connector, including an already
  active finAPI connection, through the generic `UnconfiguredConnector` placeholder and
  silently flipped it to `not_configured` on every daily run; finAPI now has its own branch.
- **Stage 3 -- matching and proposals.** New table `invoice_bank_transaction_link` (migration
  `0061`) records an automatic match (amount plus invoice number or IBAN in the purpose) as
  evidence only; `mhvp.banking.invoice_matching.propose_payment` creates a draft `PaymentOrder`
  via the existing, unchanged `payments.order_from_invoice` when nothing matches (rule
  `M11-06`, gate G2 stays closed). `POST /tickets/{id}/attach-invoice` (the only addition to
  `mhvp.tickets.routers`) sets a ticket's category to `invoice` and files the invoice's original
  document into the property's Google Drive year folder (`mhvp.documents.property_filing`,
  `GoogleDriveStore.file_in_property_year_folder`, new, alongside the unchanged `put`/
  `DRIVE_FOLDERS` mirror flow). Tests: `apps/api/tests/integration/test_m11_invoice_matching.py`.
- **Stage 4 -- portal document reference.** `GET /portal/account` rows carry a `document_id`
  when the booking behind that open item (`JournalEntry.document_id`) is a document this portal
  account may actually see (`mhvp.portal.access.visible_documents`, the same check the download
  endpoint re-runs); never a bare id the portal could not then open. Test:
  `apps/api/tests/integration/test_m11_portal_document_ref.py`.
- **Stage 5 -- CRM UI.** `FinApiConnections.tsx`/`FinApiSettingsCard.tsx` fixed a pre-existing
  bug (calls to `/api/v1/banking/finapi/...`, unreachable through the BFF proxy; corrected to
  `/api/bff/banking/finapi/...`) and gained a date-range fetch control (`FetchRangeControl`, used
  per account and per bank) and the auto-fetch switch; `InvoiceMatchPanel.tsx` on the invoice
  page shows a matched transaction or a "Zahlung vorbereiten" (draft only) form; the invoice
  matching and attach-invoice endpoints were added to the BFF allowlist. `TicketAttachInvoiceButton`
  is additive next to the appointment button another agent added to the ticket detail page.
  Tests: `FinApiConnections.test.tsx`, `InvoiceMatchPanel.test.tsx`,
  `TicketAttachInvoiceButton.test.tsx`.
- **Stage 6 -- docs.** This section; `docs/integrations/finapi.md` ("Rebuild" section: WebForm
  flow, consent renewal, history depth); `docs/rules/M11-05-credentials-never-in-crm.md`,
  `docs/rules/M11-06-payment-proposal-only-until-g2.md`, registered in `docs/rules/README.md`;
  `docs/OPEN_QUESTIONS.md` updated (V2/V3 decided per operator, history depth per bank still
  open).

Migrations of this rebuild: `0059_finapi_auto_fetch.py`, `0061_invoice_bank_transaction_link.py`
(numbered around several concurrently developed migrations by other agents on the shared
branch; `alembic heads` confirmed a single head after each stage).

### Open points (rebuild)

- History depth per bank is not modelled (`docs/integrations/finapi.md`, "wie vom Anbieter
  geliefert"); verify per bank once real contracts exist.
- `FinApiConnection.consent_valid_until` stays unset until a verified consent-expiry field is
  confirmed from finAPI (see "Zu prüfen" in `docs/integrations/finapi.md`); the CRM's "Erneut
  freigeben" action does not yet show a countdown.
- finAPI contract/licensing and the § 34 ZAG assessment (M11-40 to M11-45) remain open; per
  operator decision 25.09.2026 accounts are configured per tenant and finAPI is confirmed as the
  aggregator, but the underlying finAPI contract is still pending (see
  `docs/OPEN_QUESTIONS.md`).
- Portal/CRM UI for the account assignment step still takes a raw internal account id
  (`AssignForm`); a proper picker (search by property/unit) was out of scope for this rebuild's
  time budget and is a good next small UI task.
