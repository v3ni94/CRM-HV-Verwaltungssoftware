# components/banking

Client components of the bank screens (`/bank`, `/bank/regeln`, `/bank/abstimmung`,
`/bank/zahlungen`, `/bank/lastschriften`). They call the API only through the BFF
allowlist (`src/app/api/bff/[...path]/route.ts`); authorization stays with the API. Rule
`docs/rules/UI-BANK-01-bankoberflaeche.md`, handbook `docs/handbuch/banking.md`.

| Component | Purpose | API operations |
| --- | --- | --- |
| `TransactionList` | Daily work list: filters (account, status, direction, period), offset pagination (50 per page), booking dialog, ignore with reason, duplicate clarification, "Regel lernen", selection for the bulk confirmation | `GET /banking/transactions`, `GET /banking/accounts`, `POST /banking/transactions/{id}/(ignore|review|learn)` |
| `BookingDialog` | Booking of one transaction: proposals (take over on click, never pre-selected), free choice of open items with partial amounts and splits, contra account search (no bank, system or inactive accounts), booking text, outgoing payments, transfer pairs against the partner bank account, confirmation step | `GET /banking/transactions/{id}/posting-proposals`, `GET /accounting/ledgers/{id}/(accounts|open-items)`, `POST /banking/transactions/{id}/book`, `POST /ai/proposals/{id}/reject` |
| `BulkConfirm` | Bulk confirmation with preview: only deterministically verified stage 1 splits (`unambiguous` or rule hit), count, sums per legal entity, exceptions, then booking on confirmation | `GET /banking/transactions/{id}/posting-proposals`, `POST /banking/bulk-confirm` |
| `StatementImport` | CAMT.053 and MT940 upload, bank CSV with preview, column mapping and saved mappings per account | `POST /documents`, `POST /banking/imports`, `POST /banking/imports/csv(/preview)`, `GET/POST /banking/csv-mappings` |
| `BankReconciliation` | B09 view per statement, read only | `GET /banking/accounts/{id}/reconciliation` |
| `BankRules` | Rule life cycle: propose, approve (other person), activate with amount cap and uploaded test evidence, disable | `GET/POST /banking/rules`, `POST /banking/rules/{id}/(approve|activate|disable)`, `GET /accounting/ledgers`, `POST /documents` |
| `AutomationSwitchCard` | Tenant automation switch, read only (activation gated by ADR 0013 and step S6) | `GET /tenant/settings` |
| `MatchingMetricsCard`, `BankAccountOverview`, `FinApiConnections`, `FinTsConnections`, `OrderActions`, `DirectDebitRunActions`, `PropertyBankAccounts`, `BankAccountSelect` | Earlier bank components (metrics, accounts, connections, payment and direct debit runs) | see the component headers |

Marked hooks waiting for API operations of plan M12 step S1 (docs/OPEN_QUESTIONS.md BK2-01):
`STAGE1_REJECT_PATH` and `API_SUPPORTS_DISCOUNT` in `BookingDialog.tsx`, `REOPEN_PATH` in
`TransactionList.tsx`. Money is handled as integer cents (`bankTypes.toCents`, `fromCents`)
and sent as two decimal strings; nothing is booked without an explicit confirmation of the
signed in person. Tests: `*.test.tsx` next to each component (vitest), core path
`e2e/bank-buchen.spec.ts` (Playwright against the API).
