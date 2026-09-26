# Eigentümerabrechnung Miete/SEV (7.6, A06)

| Field | Content |
| --- | --- |
| ID | A06 |
| Title | Eigentümerabrechnung Miete/SEV |
| Scope | Legal entities `rental_owner` and `sev_owner` (never the management company, 6.9.1); any period inside one calendar year for the SEV reconciliation; drafts only, per tenant; excluded: VAT option in the statement (V21, M17-05), letter and dispatch (A07) |
| Source status | Fachliche Umsetzung of 7.6 A06 (no legal norm claimed); deposits and legal entity separation per 6.9.1 and D56 (annex C); the fee comes only from the stored fee settings (6.4); release: not released, G3 closed |
| Acceptance case | Hand computed values in `apps/api/tests/unit/test_m17_owner_statement_calc.py` and `apps/api/tests/integration/test_m17_owner_statement.py` (rental happy path, SEV with reconciliation, G3 lock 403 MHVP-GATE-0001, rights, tenant separation); no annex D case yet (task A25, LUECKENLISTE 26.09.2026) |
| Implementation | `mhvp.billing.owner_statement` (model `OwnerStatement`, table `owner_statement`, migration 0097, RLS; `build_results` pure, `collect_inputs` from the posted ledger), `mhvp.billing.owner_statement_routers` (`/api/v1/billing/owner-statements`), rule version `A06-owner-statement-v1`; CRM page Buchhaltung, Eigentümerabrechnung |
| Change reason | Task A25 (LUECKENLISTE 26.09.2026): A06 was specified, not implemented (M17-05) |

## Blocks and their sources

| Block | Source | Note |
| --- | --- | --- |
| Einnahmen | posted turnover (credit minus debit) of `revenue` accounts in the period, grouped by the payment types mapped to the account (`payment_type_account`): `rent`, `garage`, `parking`, `rent_reduction`, `other` are rents; `operating_cost_advance`, `heating_cost_advance` are advances; anything else is other revenue | Sollstellung basis; an account that mixes rents and advances is counted as other revenue and raises `INCOME-MIXED-ACCOUNT` |
| Ausgaben | posted turnover (debit minus credit) of `cost` accounts per account | with allocation category for the operating cost statement |
| Verwalterhonorar | `admin_fee_setting` of the property (rental: settings without debtor party or with the owner's party; SEV: only settings whose `invoice_debtor_party_id` is the SEV owner), `receivables.admin_fee` per interval times the intervals inside the period (calendar months, `monthly` 1, `quarterly` 3, `yearly` 12) | draft, never a posted invoice; no setting gives 0,00 and `FEE-NOT-CONFIGURED` |
| Auszahlungen | posted turnover (debit minus credit) of non bank accounts assigned to the owner's party or one of its contacts | no such account gives 0,00 and `OWNER-ACCOUNT-MISSING` |
| Offene Mietforderungen | `open_items` of the ledger at the last day of the period, kind receivable, remaining greater than zero, component from the posted receivable item | per contract and payment type |
| Kautionen | `deposit` records of the contracts of the legal entity with movements up to the cut-off (`deposit_totals`), plus the balance of segregated bank accounts (`property_bank_account.segregated`) | never liquidity; a difference raises `DEPOSIT-BANK-DIFFERENCE` and is never settled by an entry |
| Freie Liquidität | bank and cash balances minus deposits held minus open payables | formula shown in the snapshot |
| Überleitung (SEV) | latest calculated `hoa_statement` of the property's Gemeinschaft for the year, reduced to the units of the owner with SEV (ownership contracts with `sev_enabled`); newest calculated operating cost statements of the rental ledger for the same period | owner burden = HOA cost share minus costs allocated to tenants; missing statements raise `SEV-HOA-STATEMENT-MISSING` or `SEV-OPERATING-COST-STATEMENT-MISSING` |

Sum checks are findings (`SUM-*`, level `error`); an internal approval is refused while an error
finding exists. Draft entries in the period are named (`DRAFT-ENTRIES`) and never counted.

## Status model and locks

`draft` -> `calculated` (recalculation allowed) -> `internally_approved` (second person,
MHVP-GATE-0002). The PDF (`GET .../pdf`) checks release gate G3 before anything else and
answers 403 MHVP-GATE-0001 while the gate is closed. Nothing is posted; no receivable, payout
or fee arises from the statement.
