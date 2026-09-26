# mhvp.banking

Bank connectors (EBICS, aggregator, FinTS fallback, file import), transactions, rules, matching.

* Milestone: M11, M12 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.4, 6.9.7, 7.4, 8.
* Status: M11 file import (CAMT.053), statements, reconciliation, sync protocol implemented; connectors pending V2/V3. See docs/plans/M11.md.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/banking/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Bankkontenauswahl (Konten je Objekt und Rechtsträger)

Modul `account_selection.py`, Tabelle `bank_account_assignment` (Migration 0079). Nur lesend
und organisatorisch: kein Zahlungsverkehr, keine Buchung (G2 bleibt geschlossen).

- `GET /banking/accounts?property_id&legal_entity_id&q`: Konten (finAPI-verknüpft und manuell)
  mit Kontostand (finAPI-Saldo, sonst letzter Kontoauszug, sonst leer, nie erfunden), letzten
  fünf Umsätzen, Stammobjekt, Rechtsträger, Zuordnungen und Standardmarkierungen.
  Benötigt `accounting:read`.
- `GET /properties/{id}/bank-account-options`: gleiche Liste für die Objektseite mit
  `properties:read`; Kontostand und Umsätze nur mit `accounting:read`.
- `PUT /banking/accounts/{id}/assignments` (`property_id`, `purpose` hausgeld|miete|general,
  `is_default`), `DELETE /banking/accounts/{id}/assignments/{property_id}`,
  `PUT /banking/accounts/{id}/legal-entity-default`: benötigen `accounting:update`.
- Rechtsträgertrennung (Abschnitt 8, B01): ein Konto bleibt bei seinem Rechtsträger. Es ist
  nur für Objekte auswählbar, für die dieser Rechtsträger handelt (eigenes Objekt, oder
  dieselbe Partei hat dort einen eigenen Rechtsträger, etwa ein Vermieter mit mehreren
  Objekten). WEG-Konten sind nie für fremde Objekte auswählbar. Das Stammobjekt ist nicht
  lösbar. Standard Hausgeld nur für Konten der Art hoa/hoa_fee, Standard Miete nur für rent.
  Je Objekt und Zweck sowie je Rechtsträger gibt es höchstens ein Standardkonto.
- Ereignisse: `bank_account.assigned`, `bank_account.unassigned`,
  `bank_account.legal_entity_default`.
- UI: `apps/web-crm/src/components/banking/BankAccountSelect.tsx` (Dropdown mit Suche,
  wiederverwendbar), `PropertyBankAccounts.tsx` (Objektseite, Abschnitt Bank),
  `BankAccountOverview.tsx` (Bankseite).
