# Inventar der Listenlimits über 200 (AI08, GAH-208)

Stand 02.10.2026, Auswertung von `apps/api/openapi.json` (GET-Parameter `limit` und `page_size` mit Obergrenze über 200 oder ohne Obergrenze). Spezifikation Abschnitt 12 nennt `page_size` bis 200. Geändert wurde nur `/postal/jobs` (Obergrenze 500, vorher unbegrenzt, intern bereits auf 500 gekappt). Alle übrigen Zeilen bleiben unverändert; die Festlegung je Endpunkt steht als Frage AI08-01 in `docs/OPEN_QUESTIONS.md`.

| Pfad | Parameter | Obergrenze | Standard |
| --- | --- | --- | --- |
| `/api/v1/accounting/admin-fee-invoices` | `page_size` | 500 | 100 |
| `/api/v1/accounting/admin-fees` | `page_size` | 500 | 100 |
| `/api/v1/accounting/direct-debits` | `limit` | 1000 | 200 |
| `/api/v1/accounting/invoices` | `limit` | 1000 | 500 |
| `/api/v1/accounting/invoices` | `page_size` | 1000 |  |
| `/api/v1/accounting/ledgers/{ledger_id}/entries` | `limit` | 1000 | 100 |
| `/api/v1/accounting/ledgers/{ledger_id}/entries` | `page_size` | 1000 |  |
| `/api/v1/accounting/payment-runs/bank-status-reports` | `limit` | 500 | 50 |
| `/api/v1/accounting/period-locks` | `limit` | 500 | 100 |
| `/api/v1/accounting/receivable-runs` | `page_size` | 500 | 50 |
| `/api/v1/accounting/recurring-invoices` | `page_size` | 500 |  |
| `/api/v1/ai/conversations` | `limit` | 500 | 50 |
| `/api/v1/ai/knowledge` | `limit` | 500 | 200 |
| `/api/v1/automation/rule-proposals` | `limit` | 500 | 100 |
| `/api/v1/banking/automation/comparison` | `limit` | 500 | 100 |
| `/api/v1/banking/payment-orders` | `limit` | 1000 | 200 |
| `/api/v1/banking/transactions` | `limit` | 1000 | 200 |
| `/api/v1/contracts` | `limit` | 1000 | 200 |
| `/api/v1/contracts` | `page_size` | 1000 |  |
| `/api/v1/contracts/pending-approval` | `limit` | 5000 | 1000 |
| `/api/v1/contracts/pending-approval` | `page_size` | 5000 |  |
| `/api/v1/data-quality/report` | `limit` | 1000 | 200 |
| `/api/v1/deposits` | `limit` | 1000 | 200 |
| `/api/v1/deposits` | `page_size` | 1000 |  |
| `/api/v1/documents/trash` | `limit` | 500 | 200 |
| `/api/v1/imports/immoware24/files/{source_id}/rows` | `limit` | 1000 | 200 |
| `/api/v1/imports/immoware24/history/bank-links` | `limit` | 500 | 100 |
| `/api/v1/imports/immoware24/history/open-items` | `limit` | 500 | 100 |
| `/api/v1/imports/immoware24/history/tickets` | `limit` | 500 | 100 |
| `/api/v1/imports/migration/ledgers/{ledger_id}/journal` | `limit` | 2000 | 200 |
| `/api/v1/integrations/objektakte/objects/{number}/documents` | `page_size` | 500 | 100 |
| `/api/v1/mail/messages` | `limit` | 500 | 100 |
| `/api/v1/metering/assignments` | `limit` | 500 | 50 |
| `/api/v1/metering/assignments` | `page_size` | 500 |  |
| `/api/v1/objektakte/sync/deletions` | `limit` | 1000 | 200 |
| `/api/v1/postal/jobs` | `limit` | keine (jetzt 500 bei /postal/jobs) | 200 |
| `/api/v1/receipts/drafts` | `limit` | 500 | 100 |
| `/api/v1/sepa-mandates` | `limit` | 1000 | 200 |
| `/api/v1/sepa-mandates` | `page_size` | 1000 |  |
| `/api/v1/sla/alerts` | `limit` | 500 | 100 |
| `/api/v1/sla/clocks` | `limit` | 1000 | 200 |
| `/api/v1/tickets` | `limit` | 500 | 100 |
| `/api/v1/tickets` | `page_size` | 500 |  |
| `/api/v1/workspace/deadline-entries` | `limit` | 1000 | 200 |
| `/api/v1/workspace/deadlines` | `limit` | 1000 | 200 |
