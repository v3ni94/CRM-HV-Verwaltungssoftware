# Kostenkontoverteilung, Kreditorenkonten, Kostenkorrektur und Zinsbuchung (M10, Lückenliste 30.09.2026)

| Field | Content |
| --- | --- |
| ID | M10-W2 |
| Title | Ledger operations M10-01, M10-05, M10-06 |
| Scope | Ledger per legal entity (6.4, 7.2, 7.3), CRM bookkeeping pages (M10-02 to M10-04) |
| Source status | Fachliche Umsetzung (7.2, 7.3, 6.4 `ledger_account_allocation`); no norm of annex C is implemented; interest tax treatment not implemented (open question P01-01) |
| Acceptance case | `tests/integration/test_m10_ledger_ops.py` (60 % + 40 % accepted, 60 % + 30 % refused; cost transfer 120.00 EUR; interest received 3.50 EUR; creditor sync idempotent); annex D: none specific |
| Implementation | Allocation only for cost accounts, keys of the ledger property, each key once, total exactly 100 % or empty list. Creditor account per provider relation of the ledger property in range 070000 to 079999, linked to the relation when none is set, repeat without effect (B08). Cost transfer: two cost accounts, target debit, source credit. Interest: bank or reserve account against revenue (interest received) or cost (interest charged), gross amount as entered. Both create drafts only; posting, reversal and lock use the existing paths (B02 to B09). |
| Change reason | Lückenliste 30.09.2026, package P01 |
