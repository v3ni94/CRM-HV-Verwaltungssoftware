# ADR 0038: Currency column EUR only on money header tables (GAL-101)

- Status: Proposed (operator decision open, OPEN_QUESTIONS AP04-01)
- Date: 2026-10-03

## Context

Master prompt 4.1 requires "Währung immer EUR als Feld vorhanden". Before 1.71 only a few tables
(contract, bank account, fee invoice, metering) carried `currency`; journal entries, open items,
invoices, WEG statements, deposit movements and payment orders did not (gap GAL-101).

## Decision

Migration 0461 adds `currency VARCHAR(3) NOT NULL DEFAULT 'EUR'` with the check constraint
`ck_<table>_currency_eur` (`currency = 'EUR'`) to the header tables `journal_entry`, `open_item`,
`invoice`, `hoa_statement`, `deposit_movement` and `payment_order`. Line tables (`journal_line`,
`open_item_settlement`) inherit the currency of their header. Foreign currency stays blocked at
import; no conversion logic exists. Allowing another currency requires a new ADR, conversion
rules and dropping the check constraint; it is not prepared as a tenant switch.

## Consequences

- Every booked amount carries an explicit currency; a non EUR value is rejected by the database.
- Existing rows are filled with EUR by the column default (no row rewrite logic).
- The operator decides whether EUR only remains the permanent product scope (AP04-01).
