# mhvp.banking

Bank connectors (EBICS, aggregator, FinTS fallback, file import), transactions, rules, matching.

* Milestone: M11, M12 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.4, 6.9.7, 7.4, 8.
* Status: M11 file import (CAMT.053 and MT940), statements, reconciliation, sync protocol implemented; connectors pending V2/V3. See docs/plans/M11.md.
* File import: `connectors.FileConnector.parse(data, filename)` picks `camt.parse` or
  `mt940.parse` by suffix (`.sta`, `.mt940`, `.940`, `.swi`) or content (`:20:` at the start).
  MT940 is read by the public SWIFT field structure only; `:86:` stays raw text and the German
  subfield convention (`?20` to `?29`, `?30`/`?31`, `?32`/`?33`, SEPA prefixes) is marked as
  such in `raw.info`. Bank specific CSV is open (M11-02).

* Consent reminder (A29, 8.2): `tasks.consent_reminders` (beat, daily) and the 06:00 `sync_all`
  both call `tasks.remind_consent_expiry`: ten days before the effective consent expiry
  (`FinApiConnection.consent_valid_until`, else `BankConnection.consent_valid_until`) every
  member with `accounting:update` gets one in-app notification per connection and expiry date
  (kind and domain event `banking.consent_expiring`; the event is the idempotency marker), a
  past date sets `consent_expired`. Tests in `tests/integration/test_m11_finapi.py`.

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

## Zahlläufe: Freigabe, Bankrückmeldung, Rückgabe (M15, Anhang D D35 bis D38)

Modul `payments.py`, Endpunkte `/banking/payment-orders` und `/banking/payment-batches`.
Die Zahlungsdatei verlangt Gate G2 (je Mandant, standardmäßig geschlossen); alles davor ist
Vorschlag oder Entwurf, nichts löst eine Zahlung aus.

- D35 (`change_order`): `PATCH /payment-orders/{id}` erlaubt `execution_date`, `purpose`,
  `amount` und `counterpart_iban`. Ändert sich ein zahlungsrelevantes Feld (Betrag, Empfänger,
  IBAN, Ausführungsdatum, Rechnung, Konto, Verwendungszweck), werden alle Freigaben entwertet
  und der Auftrag fällt auf `draft` zurück; Ereignis `payment_order.approvals_invalidated`.
  Ein Betrag darf den offenen Posten nicht übersteigen; der Skonto bleibt nur erhalten,
  solange Betrag plus Skonto den offenen Betrag ergeben. Eine neue IBAN muss zu den
  freigegebenen Bankverbindungen des Empfängers gehören (PÜ04), sonst 409.
- D36 (`ensure_different_person`): die zwei Freigaben müssen von zwei Personen stammen.
  Geprüft werden Benutzerkonto, E-Mail und die verknüpfte Kontaktperson
  (`membership.contact_id`); ein Plattformadministrator zählt nie. Grenze: dieselbe Person
  mit zwei getrennten Kontakten ist technisch nicht erkennbar (docs/OPEN_QUESTIONS.md M15-02).
- D37: `POST /payment-batches/{id}/bank-status` mit `rejected` lässt den offenen Posten
  vollständig offen (Ereignis `payment_order.rejected` mit Grund und offenem Betrag).
  `executed` verlangt den Bankumsatz als Nachweis; eine Teilbelastung gleicht nur den
  bestätigten Teil aus (`partially_executed`, Ereignis `payment_order.partially_executed`
  mit `executed_amount` und `open_amount`). Eine zweite Teilausführung desselben Auftrags ist
  nicht vorgesehen; der Rest wird über einen neuen Auftrag gezahlt.
- D38 (`record_return`): `returned` storniert die Zahlungsbuchung mit Grund und Verweis
  (Regel 0.1.7, nie Überschreiben) und öffnet den Posten wieder. Optional wird die
  Rückgabegutschrift (`bank_transaction_id`) angegeben: sie muss auf dem auftraggebenden
  Konto liegen und dem ausgeführten Betrag entsprechen, dann wird sie als gebucht mit dem
  Storno als Buchungssatz markiert. Ein abweichender Betrag (Gebühren) wird abgelehnt;
  Gebühren werden nur mit Beleg gesondert gebucht. Wiederholte Rückmeldungen bleiben ohne
  Wirkung. Ereignis `payment_order.returned` mit `reversal_id` und `reversed_entry_id`.
- Tests: `tests/integration/test_m15_payments.py` (`test_payment_run`,
  `test_d35_to_d38_payment_release_and_bank_feedback`).

## Kennzahlen des Bankabgleichs (A45, Abnahme M12)

`matching_metrics.py` computes coverage (automatically and unambiguously assigned and posted
transactions / transactions of the period) and error rate (automatic assignments later
reversed / automatic assignments, split into corrected and cancelled) from existing data:
`bank_transaction.status`, `matched_rule_id`, `journal_entry.reversed_by_id` and later entries
with the same `bank_transaction_id`. Endpoint `GET /api/v1/banking/matching-metrics?from=&to=`
(`accounting:read`). Operational figures only; they never release the automation (7.4).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `ai_posting.py`: AI posting proposal `propose_posting` (M7-09, M12): input minimisation, tenant switch, proposal only, nothing posted
* `allocation.py`: payer's determination (Tilgungsbestimmung) parsed from the payment purpose (M12-03, D39), deterministic, no AI
* `invoice_matching.py`: invoice to bank transaction matching and draft payment proposal (M11-finapi stage 3, rule M11-06, G2 closed)
