# mhvp.accounting

Ledger per legal entity, accounts, journal, open items (MASTER-PROMPT 6.4, 6.9, 7.1 to 7.3).

* `models.py`: chart template, ledger, ledger_account, journal_entry/line, number counter,
  open_item, open_item_settlement. Migration 0010 adds immutability and balance triggers.
* `services.py`: drafts, posting (gapless numbers, ADR 0007), reversal, locking, reports,
  consistency checks.
* `routers.py`: `/api/v1/accounting/...`.
* `dunning.py`: dunning runs (7.5, M16). Settings per tenant with field level object
  overrides (`settings_for` returns `EffectiveSettings`, NULL on an object row inherits the
  tenant default, migration 0078, `docs/rules/M16-02.md`). Fees and interest only from
  configured values (`docs/rules/M16-01.md`).
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

* `defaults.py`: draft chart of accounts from annex A.1 (HVM convention excerpt), created unreleased (V8)
* `numbering.py`: outgoing invoice numbering, gapless `PREFIX-JJJJ-000001` under a locked counter row (M13-04)
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
