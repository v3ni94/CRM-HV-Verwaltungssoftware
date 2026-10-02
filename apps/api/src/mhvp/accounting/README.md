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
* `rent_invoice.py`, `rent_invoice_models.py`, `rent_invoice_routers.py`: rent invoices and standing invoices with VAT for tenancies with a VAT option, built from the receivable items, numbered gapless per legal entity and year (`MR-JJJJ-000001`, migration 0210), PDF on the tenant letterhead filed as document, cancellation only by credit note, draft watermark behind G1 (rule M13-04 section Mietrechnung, OPEN_QUESTIONS M13-04a); draft numbers `ENTWURF-JJJJ-NNNNNN` while G1 is closed (tenant switch `rent_invoice_draft_numbering`, AC03-01, rule AC03-01, migration 0360 noop)
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
- ZUGFeRD (S13-03): implemented in wave 16 (AE25), see the section below; PDF/A-3 conformance stays unverified (OPEN_QUESTIONS AE25-01).

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

## Verwalterhonorar: status cancelled and revenue posting drafts (T04, wave 5)

* `admin_fee_invoice.status` gains `cancelled` (migration 0290), set by `.../cancel` together
  with `cancelled_at`; `GET /accounting/admin-fee-invoices?status=` filters by it.
* `admin_fee_posting.py`: `GET/PUT /accounting/admin-fee-posting-config` (one row per tenant,
  manager ledger of a `manager` legal entity with receivable, revenue and optional VAT
  account; payer account numbers resolved per debtor ledger). No default accounts.
* `POST /accounting/admin-fee-invoices/{id}/posting-drafts` (accounting:approve, G1, invoice
  released): two journal drafts, one in the payer ledger and one in the manager ledger (E01),
  linked via `payer_entry_id` and `manager_entry_id`; idempotent. Credit notes mirror the
  sides. Posting uses the regular path. Rule `docs/rules/M13-07.md`, error `MHVP-ACC-0007`.

### Factual invoice review (M14-02, PÜ02, migration 0291)

* `invoice_factual.factual_check`: findings against work order (`invoice.work_order_id`, fallback
  `work_order.invoice_id`), resolution, economic plan item (budget), recurring plan (amount,
  rhythm, same month) and line arithmetic (`invoice_line.quantity`, `unit_price`), plus the
  proposed reviewer (`property.manager_user_id`). Messages also land in `invoice.findings`
  (except the responsibility proposal and the free text order hint).
* `GET /accounting/invoices/{id}/factual-check` (accounting:read), `GET/PUT
  /accounting/invoice-check-settings` (read: accounting:read, write: tenant_settings:update);
  tolerances in percent, default 0. Never changes a review status. Rule
  `docs/rules/PU02-sachliche-pruefung.md`.

## V10 Seed: Schlüsselverteilung je Konto

Vorlagenzeilen tragen `allocation_split` (Schlüsselcode und Prozentanteil, Summe 100) für Kostenkonten mit eindeutigem Schlüssel aus M10-02; 028100 hat die Art der Abrechnung Hausgeld (Entwurf). Seed idempotent, gepflegte Werte bleiben. Neue Buchungskreise übernehmen die Verteilung, wenn die Schlüssel im Objekt existieren. Regel: `docs/rules/V10-seed-kontenrahmen-verteilung.md`.

## Factual review links per object (U15-02, wave 7, V01)

`_check_factual_links` also checks that work order, resolution, plan item and invoice plan
belong to the property, legal entity or ledger of the invoice; otherwise 422
`MHVP-ACC-0008`. Rule M14-02.

## AA12 Regelregister und Prüfpunkte (01.10.2026)

`rule_register.py`: Auswahl des Registereintrags nach Abrechnungsbeginn (`select_version`), Verweis im Snapshot, Entwurfs-Prüfpunkte für HeizkostenV §§ 5 und 12 sowie CO2KostAufG §§ 5a bis 5d über `POST /accounting/rule-versions/seed-checkpoints` (ohne Rechtsfolge, siehe OPEN_QUESTIONS AA12-02 bis AA12-04). Reverse Charge erzeugt zusätzlich den Hinweis auf § 13b UStG als gesonderten Freigabepunkt (AA12-01), keine Automatik.

## AA10 Honorar, Rechnungsplan, Standardregel (01.10.2026, Migration 0312)

- `admin_fee_setting` (GA03-06): neue Felder `manager_contact_id`, `termination_date`, `due_day_rule` (`day`, `last_day`, `day_next_month`) mit `due_day`, `account_id` (Erlöskonto) und `sev_fee_amount`. Das Kündigungsdatum begrenzt den Lauf (`admin_fees.effective_end`), die Fälligkeit steht in der Antwort der Rechnungsausstellung (`due_date`), bei einer SE-Gebühr (Schuldner gesetzt) gilt `sev_fee_amount` je Einheit statt `amounts_per_unit_type`. Ändern per `PATCH /accounting/admin-fees/{id}`.
- `recurring_invoice_plan.auto_post` (GA03-07): Standard aus, nur setzbar bei freigeschalteter automatischer Buchung (sonst 409); Generierung erzeugt weiter nur Entwürfe (OPEN_QUESTIONS AA10-01).
- `provider_rule.propose_default_rule` (GA02-05): bei `create_default_bank_rule` entsteht beim Anlegen des Dienstleisterverhältnisses eine Bankregel im Zustand `proposed` (IBAN Fingerprint, Kreditorenkonto, Priorität 900), idempotent, ohne Buchung (AA10-03).
- ADR 0020 Formatversionen mit Pin Test `tests/unit/test_format_versions_pin.py` (GA03-09).

## AA11 WEG owner change (01.10.2026)

GA06-01: with `receivable_rules.enabled` an ownership contract with start, end or amount change
within the month is not prorated; the item stays manual (`OWNERSHIP_CHANGE`), see rule M13-01.

## AA01 Prüfbericht und Vermerke (01.10.2026)

* `GET /accounting/ledgers/{id}/checks?as_of=`: `findings` now include number gaps per fiscal
  year, counter against highest number (B04) and hard subledger invariants (B09); `subledger`
  and `subledger_differences` reconcile open items per debtor and creditor account against the
  ledger balance as of a date (differences are for review, they do not set `ok`).
* `GET/POST /accounting/ledgers/{id}/entries/{id}/notes`: versioned, append only notes on
  posted entries (`journal_entry_note`, migration 0303, errors `MHVP-ACC-0009`, `-0010`).
* Rule `docs/rules/AA01-pruefbericht-vermerke-jobgates.md`.
* AB01: the audit export ZIP carries `nebenbuchabgleich.csv` (subledger reconciliation per
  debtor and creditor as of the period end); the CRM reports page shows it as of the chosen
  date (`SubledgerCheck`). Runtime gate proof of `GATED_ROUTES`:
  `tests/integration/test_ab01_gate_runtime.py`.

- AB10: `due_checkpoints` and `GET /rule-versions/due-checkpoints` report reached check points (group Prüfpunkt) as a hint only (GA08-02).

## AB09: Plankennzeichen im Lauf

`POST /accounting/recurring-invoices/{id}/generate` liefert zusätzlich `auto_post_requested` und `auto_post_state` (`creditor_routers.auto_post_state`). Der Lauf bucht nie; G1 wird über den Resolver der Anwendung geprüft, der Automatikschalter über `tenant_settings.auto_posting_enabled`.

### Budget comparison and resolution coverage (Wave 16 AE14, P03-03)

`factual-check` additionally returns `budget` (planned amount of the linked plan item, `booked_before`
as the sum of other non reversed invoices minus credit notes on the same plan item, this invoice,
`remaining`, tolerance limit, `exceeded`) and `resolution` (number, date, status, subject,
`effective`, `subject_matches_plan`). New findings: `resolution_subject_mismatch` (resolution on
another economic plan) and `resolution_none_with_order` (order requires approval, invoice has no
resolution). Hints only; no threshold for a mandatory resolution is assumed (legal question,
P03-03 stays open).

Wave 17 (AF07, GAE-21): `booked_before = invoices_before - credit_notes_before + journal_lines_net`
(`budget_booked_before`). `journal_lines_net` is debit minus credit of posted journal lines on the
plan item's account, same ledger and booking year, whose entry has no invoice reference
(reversals of such entries net out; reversals of invoice postings are left out). The three
parts are returned for traceability. Order positions are not counted.

### SEPA B2B not supported (Wave 17 AF07, GAA-05)

Capturing a contact bank account with `mandate_scheme = b2b` answers 422 `MHVP-CONT-0033`; the
direct debit run excludes any non CORE mandate with a visible block reason. No B2B run
(pain.008 B2B, lead time, no refund right) exists; the decision is open (AF07-01).

## AE02: Kontenrahmen Vier-Augen-Freigabe und Prüfbericht (01.10.2026)

`chart_release.release` refuses the release by the submitter while `four_eyes_required` is on
(`MHVP-ACC-0015`, `PUT /accounting/templates/{id}/four-eyes`). `update_accounts` validates the
multi key `allocation_split` (sum 100). `defaults.with_kind_proposals` adds the `heating`
proposal; `GET /accounting/templates/{id}/coverage-report` lists gaps. Migration 0358.

## Periodensperre je Objekt und Zeitraum (P06-02, AE20)

`period_lock.py` und `period_lock_routers.py` (`/accounting/period-locks`): Tabellen `period_lock` und `period_lock_setting` (Migration 0376). Die Festschreibung des Buchungskreises bleibt; zusätzlich prüft `post` und `reverse` bei `lock_mode = object_period` die aktive Sperre des Objekts (MHVP-ACC-0030). Das Objekt kommt aus der Einheit der Zeile oder dem Objekt des Buchungskreises. Abschluss einer Abrechnung setzt die Sperre nur mit `auto_lock_on_close`; Aufhebung nur mit `reopen_enabled`, Antrag und zweiter Person. Regel `docs/rules/P06-02-periodensperre-objekt.md`.

## Steuerabzüge auf Habenzinsen (P01-01, AE05)

`ledger_ops.interest_draft` nimmt optional `capital_gains_tax`, `solidarity_tax` und `church_tax` als Beträge laut Bankbeleg an (kein Satz). Entwurf: Geldkonto Soll netto, Steuerkonten Soll, Zinserlös Haben brutto. Steuerkonten je Buchungskreis über `GET/PUT /accounting/ledgers/{id}/interest-tax-config` (Tabelle `ledger_interest_tax_config`), Abzüge je Buchung in `interest_tax_withholding` und über `GET .../entries/{entry_id}/interest-tax` (Migration 0361). Ohne Konto MHVP-ACC-0011. Die Rücklagenentwicklung (`hoa/reserves.py`) zeigt die Abzüge gebuchter, nicht stornierter Zinsbuchungen auf das Rücklagenkonto als `interest_tax_withheld` an. Regel `docs/rules/P01-01-zinsabzuege.md`.

## Nebenbuchprüfung ausgebuchter Posten (AC01-02, AE06)

`subledger_reconciliation(..., exclude_written_off)` zählt ausgebuchte Posten und Posten stornierter Buchungen getrennt (`excluded_*`) und blendet sie standardmäßig aus (Mandantenschalter `accounting_tax_settings.subledger_exclude_written_off`, Migration 0362). `/checks` liefert `excluded` und `exclude_written_off`; `nebenbuchabgleich.csv` hat die Spalte Grund. Nur Anzeige, Regel: `docs/rules/AC01-02.md`.

## Abnahmeregister (V16, AE01, Welle 16)

`acceptance_models.py`, `acceptance.py`, `acceptance_routers.py`, Migration 0357. Endpunkte unter `/api/v1/accounting/acceptance`: `GET /cases` (Parameter `status`), `GET /cases/{case_id}`, `GET /export.md`, `POST /cases/{case_id}/expected`, `PUT /expected/{id}` (nur Entwurf), `POST /expected/{id}/submit`, `POST /expected/{id}/decision` (zweite Person, `acceptance:approve`), `POST /expected/{id}/results`. Rechte `acceptance:read|manage|approve`, Rolle `acceptance_expert`. Regel `docs/rules/AE01-ACCEPTANCE.md`. Kein Gate-Effekt.

## Objekt der Buchungszeile (Q15-01, AE21, Welle 16)

`JournalLine.property_id` (Migration 0377, ADR 0023, Regel `docs/rules/Q15-01-objektspalte.md`). `line_property.resolve` setzt das Objekt in `services.write_draft` je Zeile: Angabe der Zeile (`lines[].property_id`), sonst Objekt der Einheit, sonst Objekt des Vertrags des Satzes (`journal_entry.contract_id`); Angabe gegen Einheit abweichend, unbekannte Einheit oder unbekanntes Objekt ergeben 422. `services.reverse` übernimmt das Objekt der Originalzeile. Datenbankregel für jede Schreibstelle: Check `ck_journal_line_property_with_unit` und Trigger `journal_line_property` (füllt aus der Einheit, lehnt Abweichung ab). Die Migration befüllt bestehende Zeilen je Mandant aus Einheit und Vertrag; der Guard für gebuchte Zeilen ist nur innerhalb dieser Migration ausgesetzt. Berichte: `vat-overview-by-property` gruppiert nach der Spalte; `monthly-matrix`, `income-expense` und `GET /ledgers/{id}/entries` nehmen `property_id` als Filter; `GET /ledgers/{id}/reports/line-property-drift` (`start`, `end` optional) zählt `unit_mismatch` (Befund, auch in `checks`), `contract_unfilled`, `contract_mismatch`, `ledger_mismatch` (Hinweise) und Zeilen ohne Objekt, höchstens 500 Zeilen. Die Periodensperre je Objekt (AE20, `period_lock.property_ids_of_lines`) liest die Spalte bereits mit.

## ZUGFeRD / Factur-X hybrid (S13-03, wave 16, AE25)

- `zugferd`: `build_cii` writes UN/CEFACT CII (D16B) in the Factur-X / ZUGFeRD profile EN 16931
  (guideline `urn:cen.eu:en16931:2017`) from the same frozen data and locks as the XRechnung
  (`xrechnung.load`); a credit note is type 381 with positive amounts and BG-3 reference.
  `check_cii` reads the XML back with `mhvp.receipts.einvoice` and compares it with the invoice
  plus the EN 16931 sums (BR-CO-10 to BR-CO-17, BR-CO-25, BR-E-10).
- `make_hybrid` embeds `factur-x.xml` into the letter PDF of `fee_documents.build_letter` with
  pypdf only: associated file (`AFRelationship /Alternative`, `Subtype text/xml`, `Params`),
  catalog `/AF`, unfiltered XMP (`pdfaid` part 3 B, Factur-X extension schema, `fx` values,
  Info dictionary identical), output intent `GTS_PDFA1` with the LittleCMS sRGB profile
  (Pillow), trailer ID, header 1.7. No new dependency.
- `pdfa_precheck` is an own pre-check (`mhvp-pdfa-precheck` 1.0, `official` false,
  `conformance` always `not_verified`). It lists blockers it can see and the points only veraPDF
  can decide. Known blocker: the letterhead renderer (`mhvp.documents.letters`) uses the non
  embedded standard fonts Helvetica and Helvetica-Bold, so the files are not PDF/A conform
  (OPEN_QUESTIONS AE25-01).
- API: `GET /accounting/admin-fee-invoices/{id}/zugferd.pdf` (headers
  `X-MHVP-ZUGFeRD-Findings`, `X-MHVP-PDFA-Status`, `X-MHVP-PDFA-Blockers`), `GET .../zugferd/check`
  (read right), `POST .../zugferd/document` (update right, idempotent, stores
  `zugferd_document_id` and `zugferd_check`, migration 0381). Nothing is sent or posted.
- Rule `docs/rules/S13-03-zugferd.md`.


## Payables from statement credits (AE22, P04-04, Q01-01, M15-07)

- `credit_payable_models.py`: `credit_payable_setting` (tenant switch `mode` off, subledger,
  reclass; default off; `four_eyes_required` default on; account numbers entered by the
  operator) and `credit_payable` (proposal, release, withdrawal per source and contract,
  migration 0378).
- `credit_payables.py`: candidates (posted rental statement credit on the debtor, owner
  statement from `issued` with positive payout, released deposit settlement), proposal,
  release (G3, four eyes), payout order via `banking.payment_run.order_for_payout` (G2 and
  G3), withdrawal (discard reclass draft, reverse posted reclass with G1, subledger item only
  through the reversal of the statement result entry).
- Entry kind `credit_reclass`: `_apply_open_items` creates the payable on the creditor line
  only and never a receivable on the debtor debit.
- Endpoints `/api/v1/accounting/credit-payables` (`settings`, `candidates`, list, `{id}`,
  `{id}/payout-options`, `{id}/release`, `{id}/payment-order`, `{id}/withdraw`).
- Rule `docs/rules/AE22-credit-payables.md`; booking rule open (OPEN_QUESTIONS Q01-01, AE22-01).

## Periodensperre und Guthabenposten, Nacharbeiten (Welle 17, AF04)

`period_lock.property_ids_of_lines` nutzt `coalesce(journal_line.property_id, unit.property_id)`. WEG-Abschluss (`hoa` Übergang `locked`) ruft `period_lock.lock_for_closed_statement` mit Quelle `hoa_statement` (Migration 0398, Check `ck_period_lock_source`). `admin_fee_posting` prüft die Objektsperre vorab. `services.reverse` storniert offene Zahlungsaufträge der Posten und Rechnungen der Buchung (`cancelled`) und lehnt den Storno ab, solange ein Auftrag bei der Bank liegt. `DELETE /ledgers/{id}/entries/{entry_id}` lehnt Umbuchungsentwürfe eines Guthabenpostens mit 409 ab.

## AF06 (Welle 17)

* `POST /accounting/recurring-invoices/{id}/generate` bleibt Entwurf mit Planentwurfsnummer
  (`PLAN-...`, nie MR-Kreis). Im Mandantenschalter `reject_when_g1_closed` (AC03-01) weist die
  Route bei geschlossenem G1 mit MHVP-GATE-0001 ab. Antwort enthaelt `draft_number` und
  `g1_open`. Register: `GATE_CONDITIONAL_ROUTES` in `tests/unit/test_ga14_gate_coverage.py`.
* `GET /accounting/g1-opening` liefert `acceptance_register` (lesend, Stand des
  Abnahmeregisters, Link `/plattform/abnahme`); `g1_acceptance` wird nie ueberschrieben.


### Mandantenweite Zusammenfassung Zinsabzug (AF24, GAE-38)

`GET /accounting/interest-tax-config` (Leserecht, keine Parameter) liefert `ledgers_total` und `ledgers_configured` (Buchungskreise mit mindestens einem Steuerkonto). Rein lesend. Die Seite Fachliche Regeln zeigt damit den Zinsabzug und, über `GET /document-text-blocks/codes`, die freigegebenen Textbausteine als Zahl statt nur als Link.

## AG11: Leselisten und Objektfilter (Welle 18)

- `GET /accounting/ledgers/{id}/payment-type-accounts` liefert die bestehenden Zuordnungen Zahlungsart zu Konto (Recht `accounting:read`, nur eigener Mandant, unbekannte Query-Parameter 422).
- `GET /accounting/direct-debits/creditor-ids` liefert die hinterlegten Gläubiger-IDs je Rechtsträger und den Rückfall des Mandanten (nur lesend).
- `GET /accounting/ledgers/{id}/reports/xlsx` kennt den Filter `property_id` für Journal, Monatsmatrix und Einnahmen Ausgaben (Objekt der Buchungszeile); bei Auswertungen ohne Objektachse antwortet die API mit 422.

## Leading system per process kind (AG02, GAC-05)

`ledger_leading_switch` (migration 0420, RLS) holds switches per ledger, optional property,
kind (`receivable_posting`, `dunning`, `direct_debit`, `payment_order`) and `valid_from`.
`leading.is_leading(session, ledger, kind, on_date, property_id=None)` is the single check of
the dunning run, direct debit run, payment run and bank auto posting; it falls back to
`Ledger.leading_system`. The receivable run blocks only on an explicit approved switch to the
legacy system (comparison postings stay, M10-05). Requests: `POST
/accounting/ledgers/{id}/leading-switches`; decision by another person: `POST
.../{switch_id}/decide` (G1 when the platform becomes leading). Rule AG02-01.

## Liquidity report variant (wave 20, AI02, GAH-104)

`GET /accounting/ledgers/{id}/reports/liquidity` returns the 90 day preview with the common
`report_header` (legal entity, key date, data state, filter `horizon`, draft status) and runs the
legal entity scope check. `liquidity` is part of `ReportName`, so `reports/xlsx?report=liquidity`
exports it. Each account row carries `kind_basis` (`bank_account`, `number_convention` for the
001201 fallback, `default`). The raw `GET /ledgers/{id}/liquidity` stays for compatibility.

### § 35a basis switch (AI18, GAH-101)

`AccountingTaxSettings.section_35a_basis` (`invoice_date` default, `payment_date`) selects the lines of `section35a_summary`; `invoice_payment_states` derives paid and payment date from the settlements of the invoice's open items. Every generated certificate is recorded in `section35a_certificate_log` (no lock, `repeat_notice` on repeats). Rule AI18-01.

## Default interest day count and Basiszinssatz hint (AI03, rule AI03-01)

`GET/PUT /accounting/dunning-interest` reads and sets the tenant switch
`tenant_settings.sources.dunning_interest_day_count` (`act_365_fixed` default, `act_act`);
every interest period carries `day_count`. The same GET reports `base_rate_stale` with a hint
when no Basiszinssatz is maintained for the current half year; `POST
/accounting/dunning-interest/base-rate-checkpoints` seeds draft check points for the next two
change dates. Concurrency of payment approval, bank status, dunning approval and direct debit
approval is covered by the `test_ai03_*` tests (GAH-112).

## Nummernkreis Bank und Kasse (AI01, GAH-105)

`POST /ledgers/{id}/accounts` weist Konten im Bereich 001200 bis 001999 mit anderer Kategorie als bank, cash, technical oder transit und Bankkontoverknüpfungen an anderen Kategorien als bank oder cash mit 422 `MHVP-ACC-0032` ab (`accounting/chart_rules.py`). Bestehende Konten tragen in der Kontenliste den Hinweis `range_warning`. Regel AI01-01.
