# mhvp.accounting

Ledger per legal entity, accounts, journal, open items (MASTER-PROMPT 6.4, 6.9, 7.1 to 7.3).

* `models.py`: chart template, ledger, ledger_account, journal_entry/line, number counter,
  open_item, open_item_settlement. Migration 0010 adds immutability and balance triggers.
* `services.py`: drafts, posting (gapless numbers, ADR 0007), reversal, locking, reports,
  consistency checks.
* `routers.py`: `/api/v1/accounting/...`.
* `settlement.py`: settlement proposal in the statutory order (M10-03, 7.4 Nr. 5, D39):
  pure `propose` with `RULE_VERSION`, `items_for` (open receivables of a debtor with claim
  class and dunning burden), `determination_from_purpose` (reuses the bank purpose parser).
  `POST /ledgers/{id}/open-items/settlement-proposal` computes only; `.../confirm` recomputes,
  checks the fingerprint, writes a draft `debtor_payment` with the settlement plan and the
  audit event `open_item_settlement.proposal_confirmed` (rule version); `post_immediately`
  needs G1 (`docs/rules/M10-03-tilgungsfolge-vorschlag.md`).
* `dunning.py`: dunning runs (7.5, M16). Settings per tenant with field level object
  overrides (`settings_for` returns `EffectiveSettings`, NULL on an object row inherits the
  tenant default, migration 0078, `docs/rules/M16-02.md`). Fees and interest only from
  configured values (`docs/rules/M16-01.md`).
  Completion M16-20 (migration 0254, `docs/rules/M16-20.md`): delivery proofs per sent case
  (`/dunning-cases/{id}/delivery-proofs`), Basiszinssatz history with source
  (`/dunning-interest-rates`, pro rata split per period, `interest_detail` on the case),
  structured blocks per open item (`/open-items/{id}/dunning-blocks`, `/dunning-blocks`),
  check hints on the case (`check_hints`, no computed limitation date), interest as draft
  receivable only on request (`/dunning-cases/{id}/interest-draft`, account 489100) and a
  spread proposal from the debtor's consumer flag (`interest_spread_suggestion`, never
  applied).
* `dunning_letters.py`: dunning letter as PDF draft on the tenant letterhead
  (`mhvp.documents.letters`, DIN 5008). `POST /dunning-cases/{id}/letter-preview` (PDF, not
  filed), `POST /dunning-cases/{id}/letter` (filed, linked to the case), `POST
  /dunning-cases/{id}/letter/send` always refuses (G1 closed; dispatch not released, M16-02).
  Text modules per level (`STANDARD_TEXTS`, neutral) with the claim table (`ClaimTable`) and
  placeholders in `letter_text` (`PLACEHOLDERS`; `POST /dunning-settings/letter-preview`
  renders a level with sample items, A33). Mahnbescheid preparation as PDF: `POST
  /dunning-cases/{id}/mahnbescheid-preview` and `POST /dunning-cases/{id}/mahnbescheid`
  (filed), notice "Vorbereitung, Prüfung durch Rechtsanwalt erforderlich, kein Antrag" (A31).
* `xrechnung.py`: Verwalterhonorar invoices as XRechnung (UBL 2.1, XRechnung 3.0, A12,
  `docs/rules/M13-04.md`). `POST /admin-fees/{id}/invoice-issue` freezes the issued invoice
  (`AdminFeeInvoice`, migration 0094); `GET /invoices/{id}/xrechnung.xml` renders it,
  `GET /invoices/{id}/xrechnung/check` lists structural findings, `POST
  /invoices/{id}/xrechnung/document` files it once. Leitweg-ID, tax data and payee IBAN come
  only from `TenantBillingSettings`, company data from `TenantSettings.company`; missing values
  lock with MHVP-BILL-0002/0003/0005/0007. Official validation: `scripts/kosit_validate.sh`.
* Gate: declaring the platform as leading system requires G1. Until then ledgers run in
  parallel to Immoware24 and are not the leading bookkeeping.
* Rules: `docs/rules/B01.md` to `B09.md`. Plan: `docs/plans/M10.md`.

## Direct debits (pain.008, M15, rule M15-02)

* `direct_debit.py`, `direct_debit_models.py`, `direct_debit_routers.py`
  (`/api/v1/accounting/direct-debits`): due receivables of a ledger are collected from the
  contract party's contact bank account with an active SEPA mandate (rule M3-02); items
  without a usable mandate are listed with a reason and never collected.
* Sequence type FRST on first use, RCUR after a run was handed out; creditor id from the
  legal entity or the tenant billing settings (never invented); collection date and lead days
  are mandatory parameters.
* Two person approval on a snapshot; `POST /{id}/file` builds, checks and files the
  pain.008.001.02 as a document; `GET /{id}/file` requires release gate G2. Nothing is sent to
  a bank. Pre-notifications are drafts per payer via `mhvp.communication.dispatch`.
* Rule: `docs/rules/M15-02-pain008.md`. Plan: `docs/plans/M15.md`. Open: M15-01.


### Bank feedback and lead days (M15-01, M15-06, rule M15-03)

`direct_debit_feedback.py` records per order `accepted`, `rejected`, `collected` (actual
amount) or `returned` (reason code) after the file was handed out, manually via `POST
/accounting/direct-debits/{run_id}/bank-status` or from an imported report; nothing is posted.
`GET /{run_id}/reconciliation` compares each order with its open item. Lead days per sequence
type (`dd_lead_days_frst`, `dd_lead_days_rcur`) and pre-notification days from
`payment_bank_config` are enforced only when entered (zu verifizieren); without them the
pre-notification result carries a warning. B2B stays blocked (M15-05).

## Audit export (7.7, A26, D55, rule M18-02)

* `audit_export.py`, `audit_export_routers.py` (`/api/v1/accounting/audit-exports`): one ZIP
  per ledger (= legal entity) and period with a semicolon CSV per table (accounts, entries,
  lines, reversal relations, opening balances, open items, settlements, approvals, events,
  master data with audit log history, allocation keys and values, receipts), the linked
  original receipts as files below `receipts_max_bytes` (otherwise reference list with
  SHA-256), `export.json` and `index.csv`/`index.json` with row count, columns and SHA-256 per
  file. UTF-8 with BOM, CRLF, decimal comma, ISO dates, `csv_safe_cell` on every text cell.
* Recorded as `ExportRun` (format `audit_zip`, status `queued`/`running`/`done`/`failed`,
  params, SHA-256 of the ZIP, creator, finish time; migration 0096) and filed as generated
  document of the legal entity. Inline up to 2.000 posted entries, otherwise Celery task
  `mhvp.accounting.audit_export_run`.
* Permissions: `accounting:read` lists and reads status, `accounting:export` creates and
  downloads. Only posted entries; no DATEV chart of accounts, no tax classification, no GoBD
  data carrier format or description standard (M18-01, P05).
* Rule: `docs/rules/M18-02-pruefexport.md`. Tests: `tests/integration/test_m18_audit_export.py`,
  `tests/unit/test_audit_export_csv.py`.

### DATEV account mapping (A36, M18-01, rule M18-04)

* `datev_mapping.py`, `datev_mapping_routers.py`, table `datev_account_mapping` (migration
  0099): operator maintained assignment of CRM account numbers to DATEV Sachkonten per tenant,
  optionally per ledger (ledger row wins) and valid from a date (latest validity not after the
  booking date wins). Nothing is preloaded, no SKR03/SKR04 chart is shipped.
* `/api/v1/accounting/datev-mappings`: list, create, patch, delete, `import` (CSV with header
  `account_code;datev_account;label;valid_from`, German aliases, `dry_run` preview, a file with
  row errors is not written), `report` (unmapped accounts per ledger and period).
  `accounting:update` maintains, `accounting:read` lists and reports.
* `reports.datev_csv` writes the resolved DATEV account in "Konto" and refuses with
  `409 MHVP-BILL-0008` and the list of missing accounts (`missing`) when a posted line in the
  period has no mapping; raw CRM numbers are never written. Tests:
  `tests/integration/test_m18_datev_mapping.py`.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `defaults.py`: draft chart of accounts from annex A.1 (HVM convention excerpt), created unreleased (V8); since 26.09.2026 (M10-01, rule `docs/rules/M10-01-kontenrahmen-vorlage.md`) also the
  proposed rental revenue accounts 060300 to 060800 with `review_status = "entwurf"` and note
  "Freigabe durch Steuerberatung offen" (`LedgerAccount.review_status`, migration 0137).
  `default_template` is idempotent and only appends template rows whose number is missing
  Since 26.09.2026 (M10-02, rule `docs/rules/M10-02-kostenkonten-vorbelegung.md`) the cost
  accounts are pre-set as a draft following the BetrKV catalogue (`COSTS`, `BETRKV_TYPES`):
  allocable with `statement_kind = "operating_costs"` and a proposed key code
  (`allocation_key_code`, annex A.2) or not allocable; VAT option stays unset; 041805 stays
  unclassified. `fill_unset` fills only unset fields of existing template rows (never operator
  edits) and marks filled rows as drafts; existing ledgers are untouched.
* `proration.py`: pure receivable rules M13-01 to M13-03 (`docs/rules/M13-01.md` to
  `M13-03.md`): pro rata month by calendar days, 30/360 or full month with 8 decimal
  intermediates, half up rounding and the rounding difference on the last segment; quarterly,
  semiannual and annual instalments in advance or in arrears; VAT split. Used by
  `receivables.compute` only when `TenantSettings.receivable_rules.enabled` is set (default
  off); the calculation path is stored in `ReceivableRun.calculation`; posting such a run needs
  release gate G1. The output tax account is mapped under the reserved code `vat_output`.
* `numbering.py`: outgoing invoice numbering, gapless `PREFIX-JJJJ-000001` under a locked counter row (M13-04)
* `rent_invoice.py`, `rent_invoice_models.py`, `rent_invoice_routers.py`: rent invoices and standing invoices with VAT for tenancies with a VAT option, built from the receivable items, numbered gapless per legal entity and year (`MR-JJJJ-000001`, migration 0210), PDF on the tenant letterhead filed as document, cancellation only by credit note, draft watermark behind G1 (rule M13-04 section Mietrechnung, OPEN_QUESTIONS M13-04a)
* `schemas.py`: API schemas of the ledger (6.4), money as decimal strings, never float (6.9.8)
* `tasks.py`: Celery job `accounting.dunning_run` (15.1, monthly on the 5th), preview runs only, never sent

## Performance (Review 26.09.2026)

Journal (`GET /ledgers/{id}/entries`), invoices (`GET /invoices`) and direct debit runs
(`GET /direct-debits`) build their output in batches (`_outs` with `services.entry_lines_of`,
`_invoices_full`, `_runs_out` with `direct_debit.orders_of_runs` and
`valid_approvals_of_runs`). Journal and invoices paginate in the pattern of `GET /tickets`
(`page`, `page_size`, headers `X-Total-Count`, `X-Page`, `X-Page-Size`; the journal keeps
`limit`/`offset`). New indexes (migration 0127): `journal_entry(tenant_id, ledger_id, status |
booking_date)`, `journal_line(journal_entry_id)`, `journal_line(account_id)`,
`invoice(tenant_id, ledger_id)`, `invoice(tenant_id, review_status, invoice_date)`,
`invoice_line(invoice_id)`, `invoice_review(invoice_id)`,
`direct_debit_run(tenant_id, status, collection_date)`. See
`docs/reviews/2026-09-26-performance.md`.

## Steuerentwürfe (M14-02, M14-03, M14-04, 27.09.2026)

* `tax_models.py`: `accounting_tax_settings` (Schalter je Mandant, Standard aus: Vorsteuer,
  Bauabzugsteuer mit Prozentsatz, § 35a, Freigabegrenzen je Rolle), `property_tax_profile`
  (Umsatzsteueroption, Umsatzschlüssel), `supplier_tax_profile` (Bauleistung, Reverse Charge,
  Freistellungsbescheinigung mit Gültigkeit und Dokument), `invoice_tax_data` (Steuersatz,
  Vorsteuer, Vorschläge, Warnungen, bestätigter Einbehalt), `invoice_line_section35a` (Art,
  Lohnanteil, Materialanteil), `invoice_second_approval` (Migration 0185).
* `tax.py`: reine Rechenfunktionen mit vorgerechneten Tests (`tests/unit/test_m14_tax.py`),
  `refresh_proposals` (deterministische Vorschläge und Warnungen), `assert_posting_allowed`
  (Haken in `invoices.post`: zweite Freigabe über der Grenze, unentschiedener Einbehalt),
  `section35a_summary` (Ausweis je Mietvertrag).
* `tax_routers.py`: `/accounting/tax/...` (Einstellungen mit `tenant_settings:update`, Profile
  und Rechnungsdaten mit `accounting:update`, Freigaben mit `accounting:approve` durch eine
  andere Person, § 35a-Ausweis als JSON, PDF-Entwurf und abgelegtes Dokument). Regeln:
  `docs/rules/M14-02.md`, `M14-03.md`, `M14-04.md`, Quellenstatus zu prüfen durch Steuerberater.

### DATEV batch self check and chart of accounts release (M18-01, M10-01/M10-02, V8)

* `datev_check.py`: pure formal check of a Buchungsstapel file (rules DC-01 to DC-22, each
  with source status `belegt` or `zu_pruefen`; only documented rules produce errors), text
  report and the 20 line sample batch for the tax advisor. `datev_check_routers.py`:
  `/api/v1/accounting/datev/exports`, `.../exports/{id}/check` (POST runs, GET returns JSON
  or text), `.../exports/{id}/download`, `/check-file`, `/sample-batch`. Export runs keep
  their file (`export_run.content`, migration 0190). Rule `docs/rules/M18-06`.
* `chart_release.py`, `chart_release_routers.py`: template status draft, in_review,
  released (date, releaser, comment, optional tax advisor document), new version after a
  change (`supersedes_id`), history, CSV/PDF export. Gate G1 is approved only with a
  released template (`MHVP-GATE-0004`, checked in `mhvp.platform.routers._decide`).

## Reversal reason code (B03 addendum 28.09.2026, ADR 0014)

`services.reverse` takes `reason_code: ReversalReason` (`input_error`, `wrong_assignment`,
`wrong_amount`, `wrong_date`, `duplicate`, `bank_return`, `run_reversal`, `automation_error`,
`other`; default `other`) next to the mandatory free text; the code is stored on the reversal
entry (`journal_entry.reversal_reason_code`, migration 0232) and carried by the event
`journal_entry.reversed` together with `bank_transaction_id`. `ReverseIn.reason_code` is
optional for clients. Bank returns pass `bank_return`, run reversals `run_reversal`. The bank
side consumes the event in `mhvp.banking.events_consumer`; accounting never imports banking.
Index `ix_journal_entry_bank_transaction` (tenant, bank transaction, partial) serves that lookup.

## G1 opening checklist (M12-09, 29.09.2026)

`g1_opening.py` and `g1_opening_routers.py`: `GET /accounting/g1-opening` derives the state of
the opening list (released chart of accounts, accepted annex D cases, manual items, automation
levels, gate G1 state and requests, document paths); `PUT /accounting/g1-opening/items/{key}`
records the operator's result per annex D case or manual item in the table `g1_acceptance`
(migration 0242, RLS, `accounting:approve`); `POST /accounting/g1-opening/request` files a
regular `release_gate_request` for G1 with an evidence line composed from the checklist
(`release_gates:create`, person only). The decision stays with a second person on the platform
page (ADR 0003); nothing here opens a gate. Operator documents:
`docs/acceptance/kontenrahmen-pruefung.md`, `docs/acceptance/abnahme-anhang-d.md`,
`docs/handbuch/verfahrensdokumentation.md` chapter 7. Tests: `tests/integration/test_g1_opening.py`.

## Ledger operations (gap list 30.09.2026, package P01)

`ledger_ops.py`: cost account allocation (`GET/PUT /ledgers/{id}/accounts/{aid}/allocations`,
cost accounts only, keys of the ledger property, total exactly 100 % or empty), creditor
accounts per provider relation (`POST /ledgers/{id}/sync-creditors`, idempotent, links the
relation; `ensure_creditor_for_relation` for the properties module), dedicated drafts for
cost transfer (`POST /ledgers/{id}/entries/cost-transfer`, `EntryKind.COST_TRANSFER`) and
interest (`POST /ledgers/{id}/entries/interest`, `EntryKind.INTEREST`, gross amount, no tax
logic, OPEN_QUESTIONS P01-01). `AccountPatch` also takes `vat_option` and
`relevant_for_cash_report`. Rule: `docs/rules/M10-W2-ledger-ops.md`. CRM pages:
`/buchhaltung/[id]` (entry form, journal actions, lock), `/buchhaltung/[id]/konten`,
`/buchhaltung/[id]/konten/[accountId]` (sheet, allocation).
* `report_views.py`, `report_xlsx.py`, `report_routers.py`, `procedure_doc.py` (P10, migration 0259,
  `docs/rules/P10-auswertungen.md`, `P10-steuerentwurf.md`, `S711-11-regelversion.md`): header per
  evaluation (legal entity, period, key date, data state, filters, draft), month matrix, target/actual
  receivables, bank account statement with bank balance comparison, XLSX output, draft VAT overview
  and income/expense view (no EÜR), tax flags per account (`eur_relevant`, `ust_relevant`,
  `mixed_use_review`, set by `accounting:approve`), rule version register, procedure documentation
  draft from operating data. Audit export: tables `vertraege` and approvals of dunning runs and
  payment orders in `freigaben`.

## Receivable evidence and Verwalterhonorar lifecycle (gap list 30.09.2026, package P02)

Rule `docs/rules/M13-05.md`, migration 0251.

- Receivable items carry their legal basis (`contract_version`, `payment_schedule_id`,
  `basis_valid_from`, `basis_reason`, `basis_document_id`). A month already posted whose
  recomputed amount differs yields a manual difference item (`difference_of_item_id`,
  `difference_amount`); it is never posted, the correction is reversal plus new run.
- `GET /accounting/receivable-runs` lists runs (filters `period_month`, `scope`, `scope_id`,
  `status`, paginated); the run detail filters items by `item_status`, `contract_id`,
  `payment_type_code`.
- Job `mhvp.accounting.receivable_run` (beat on the 1st, 05:00): preview only, per tenant with
  `receivable_rules.monthly_preview_enabled`, once per month (scope `all`).
- `mhvp.accounting.admin_fees`: list, read, change, end and delete (only without invoices) of
  fee settings; `GET /accounting/admin-fees-periods` previews due service periods;
  `invoice-issue?period_start=` issues one invoice per calendar aligned period
  (`uq_admin_fee_invoice_period`); invoices can be listed, read, released and cancelled by a
  credit note with its own gapless number. Credit notes produce no XRechnung yet (409).
- The fee revenue posting is not implemented (OPEN_QUESTIONS P02-02, G1).

## Invoice review checks, creditors, recurring plans (gap list 30.09.2026, package P03)

- `invoice_checks`: further PÜ01 to PÜ04 findings (mandatory data checklist, service period
  plausibility, stated discount, prepayment and retention, reverse charge and construction
  withholding markers, service contract coverage, affiliation and conflict hints, credit note
  reference and limit, content hash duplicates, IBAN against the superseded version). Called
  from `invoices.evaluate`; hints only. `invoices.post` refuses a credit note whose reference
  check fails (409).
- `creditor_routers` (mounted by `routers`): `GET /accounting/ledgers/{id}/creditors`,
  `.../creditors/{account_id}/open-items`, `.../statement`; `GET/PATCH/DELETE
  /accounting/recurring-invoices[/{id}]`, `POST .../{id}/end`. Plans keep an anchor day for
  month ends and link generated invoices by `invoice.recurring_plan_id`.
- `xrechnung_credit`: UBL CreditNote 381 with BillingReference for a cancelled Verwalterhonorar
  invoice (`GET /accounting/admin-fee-invoices/{id}/xrechnung-credit-note.xml` and `/check`).
- Migration 0252; rule `docs/rules/M14-PU-W2-rechnungspruefung.md`.

## Fee documents, fee run, VAT by object, year carry over (Q15, 30.09.2026)

- `fee_documents`: PDF invoice document on the tenant letterhead for a fee invoice or credit note
  (`POST /accounting/admin-fee-invoices/{id}/document`, stored in `pdf_document_id`, migration 0282),
  credit note XRechnung filed as document, batch issue `POST /accounting/admin-fees-run`
  (preview without `confirm`, one savepoint and one gapless number per invoice). Rule `docs/rules/Q15-fee-documents-carryover.md`.
- `report_views.vat_overview_by_property`: VAT by object (via the unit of the line) and cost center.
- `year_carryover`: closing balances to opening balances as two drafts with four eyes.
- ZUGFeRD (S13-03) is not implemented: no PDF/A-3 library available offline (OPEN_QUESTIONS Q15-03).

## Approval decisions, person check, open item balances (Q01, 30.09.2026)

- `approval_decisions`: central `approval_decision` (subject `payment_order` or `invoice`, step,
  `subject_snapshot_hash`, status `valid`/`invalidated`, legacy reference, warnings), written next
  to `payment_approval`, `invoice.released_hash` and `invoice_second_approval` (S69-02). A changed
  subject persists `invalidated`. `person_warnings` compares contact e-mails and name plus birth
  date of the linked contacts and only warns (S69-03). `GET /accounting/approval-decisions`.
- `open_item_balances`: maintained table `open_item_balance` per cut-off date (RLS, no
  materialized view), refreshed nightly by `mhvp.accounting.open_item_balance_refresh` (job key
  `accounting-open-item-balance`) or via `POST /accounting/ledgers/{id}/open-item-balances/refresh`
  (S69-04). The live computation stays the source of truth.
- `properties.routers.add_provider` calls `ledger_ops.ensure_creditor_for_relation` (M10-05).
- Migration 0271. Rule: `docs/rules/Q01-approval-decisions-open-items.md`.

## CRM-Oberflächen Welle 4 (R01)

Keine API-Änderung. Neue CRM-Komponenten: `AdminFeeRun` (Honorarlauf mit Vorschau, `POST /accounting/admin-fees-run`), PDF-Ablage und Download der Honorarrechnung (`POST /accounting/admin-fee-invoices/{id}/document`, Datei über `/api/handover-files/documents/{id}/content`), `YearCarryoverPanel` (`GET` und `POST /accounting/ledgers/{id}/year-carryover`, nur Entwürfe), `RecurringPlanCreate`, Anlagenfeld in `InvoiceCreate`, Sammelrückmeldung der Lastschriften (`POST /accounting/direct-debits/{id}/bank-status` mit mehreren `order_ids`, Test `test_direct_debit_batch_feedback`).
