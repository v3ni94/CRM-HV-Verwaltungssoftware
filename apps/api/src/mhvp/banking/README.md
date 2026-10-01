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

* finAPI (M11-01, operator decision 26.09.2026: aggregator finAPI first, file import stays,
  EBICS later): `finapi.py` holds `FinApiClient` (httpx, fake transport in tests) and
  `FinApiConnector` behind the `BankConnector` seam, read only (accounts, balances,
  transactions; no payment initiation, G2 closed). Token flow: client credentials for
  `POST /users` (one technical finAPI user per bank connection, auto update off, id and
  password stored encrypted on `FinApiConnection`), password grant user token for every data
  call. WebForm import stores only form id, URL and status. Incremental sync per account from
  `FinApiAccountLink.last_synced_booking_date` minus `tasks.SYNC_OVERLAP_DAYS`, idempotent by
  `bank_reference = "finapi:<id>"` (D05), amounts as `Decimal`. Errors: `MHVP-BANK-0001` to
  `0006` (0005 credentials rejected, 0006 rate limit with `Retry-After`, no retry loop). Default
  base URL by data center from `Settings.finapi_base_url_sandbox`/`_live`. Migration 0141.
  Spec and open points: `docs/integrations/finapi.md`; tests `tests/unit/test_finapi_client.py`,
  `tests/integration/test_m11_finapi.py`.

* FinTS/HBCI PIN/TAN (M11-01 addendum, operator decision 27.09.2026, in addition to finAPI):
  `fints.py` holds the institute lookup (`data/fints_institutes.txt`, externally maintained,
  `search_institutes`, `blz_from_iban`), the pause/resume workflow on top of
  `fints.client.FinTS3PinTanClient` (`start_session`/`continue_session`, opaque blobs from
  `deconstruct`/`pause_dialog`/`get_data`, `Progress` for a TAN in the middle of the work)
  and the return code mapping (`MHVP-BANK-0007` to `0016`). `fints_routers.py` exposes
  `/banking/fints/*` (institutes, connections, sessions, tan, refresh, assign, delete);
  `tasks.fints_step` (queue `bank`) runs one blocking step per session outside any database
  transaction and persists to `bank_fints_session`. Login, PIN and client state are stored
  encrypted on `FinTsConnection`; a rejected PIN is discarded (no automatic retry). Migration
  0161, spec `docs/integrations/fints.md`, rule M11-07, tests `tests/unit/test_fints.py`,
  `tests/integration/test_m11_fints.py` (fake client `tests/fints_fake.py`).

* Consent reminder (A29, 8.2): `tasks.consent_reminders` (beat, daily) and the 06:00 `sync_all`
  both call `tasks.remind_consent_expiry`: ten days before the effective consent expiry
  (`FinApiConnection.consent_valid_until`, else `BankConnection.consent_valid_until`) every
  member with `accounting:update` gets one in-app notification per connection and expiry date
  (kind and domain event `banking.consent_expiring`; the event is the idempotency marker), a
  past date sets `consent_expired`. Tests in `tests/integration/test_m11_finapi.py`.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/banking/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Transferpaare buchen (D04, Regel B08)

Der Import verknüpft Umbuchungen zwischen eigenen Konten desselben Rechtsträgers über
`transfer_pair_id` (`services.pair_transfer`). `POST /banking/transactions/{id}/book` bucht ein
Paar genau einmal, von einer beliebigen Seite, gegen das Sachkonto des Partnerbankkontos (ohne
Postenausgleich, ohne Skonto, sonst 422). Die Buchung bewegt beide Bankkonten; die Partnerseite
erhält Status `booked` und dieselbe `journal_entry_id`. Ein weiterer Buchungsversuch auf die
Partnerseite, auch in `/bulk-confirm`, endet mit 409 `MHVP-BANK-0019`, solange eine nicht
stornierte Umbuchung auf einer Seite liegt. `matching.lock_for_booking` sperrt beide Seiten in
stabiler Reihenfolge (`ORDER BY id ... FOR UPDATE`), damit parallele Buchungen der beiden Seiten
nacheinander laufen. Nach dem Storno der Paarbuchung (`/accounting/.../entries/{id}/reverse`) ist
das Paar wieder genau einmal buchbar. Umsätze ohne Paar sind unverändert. Tests:
`tests/integration/test_annex_d_gaps.py::test_d04_*`.

Erledigt wird ein Paar nur durch eine echte Umbuchung, also eine wirksame Buchung der
Partnerseite mit einer Zeile auf dem Bankkonto dieser Hälfte. Wurde die Partnerseite vor der
Paarerkennung gegen ein anderes Konto gebucht (typisch Geldtransit, wenn Auszug B später kommt),
bucht man diese Hälfte eigenständig gegen ein Gegenkonto (üblich Geldtransit, das damit
ausgeglichen wird; ohne Postenausgleich, ohne Skonto, nicht gegen das eigene Bankkonto). Gegen
das Partnerbankkonto wird sie mit 409 `MHVP-BANK-0020` abgelehnt, weil dieses Konto sonst ein
zweites Mal bewegt würde; die Meldung nennt das Konto der Partnerbuchung. Für eine direkte
Umbuchung ist zuerst die Buchung der Partnerseite zu stornieren. `pair_transfer` verknüpft
auch bereits gebuchte Umsätze; die Verknüpfung dient der Anzeige und sperrt allein nichts
(Regel B08, Änderung 28.09.2026).

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

### Zahlungsdatei, Einreichung, Download-Protokoll (M15-01, M15-03, V2; 27.09.2026)

- `pain001` erzeugt pain.001.001.03 oder pain.001.001.09 (Vorgabe 09), Version je
  Auftraggeberkonto in `payment_bank_config` (`GET/PUT /banking/payment-bank-config/{account}`,
  außerdem `pain008_version` und `submission_channel`). Beide Versionen werden in
  `tests/unit/test_pain001_versions.py` gegen die ISO-20022-XSDs unter `tests/data/iso20022/`
  validiert; `validate_pain001` prüft Struktur, Anzahl, Kontrollsummen und EndToEndId.
- `POST /banking/payment-batches` (G2, Vier-Augen je Auftrag) legt die Datei als Dokument
  ab und speichert `transaction_count`, `control_sum` und `file_sha256`; Status
  `file_generated`. `GET /banking/payment-batches/{id}/file` (G2) prüft die abgelegten Bytes
  gegen die Prüfsumme, protokolliert den Download in `payment_file_download` (Ereignis
  `payment_batch.downloaded`) und liefert `X-Content-SHA256`.
- `payment_submitters.PaymentSubmitter`: `FileDownloadSubmitter` (manueller Upload im
  Onlinebanking, `POST /banking/payment-batches/{id}/submit` mit Bankreferenz nach mindestens
  einem Download, Status `submitted`), `FintsSubmitter` und `ebics.EbicsSubmitter` als
  Gerüste, die mit `MHVP-BANK-0017` ablehnen (Feature-Flags `MHVP_FINTS_PAYMENT_SUBMISSION`,
  `MHVP_EBICS_PAYMENT_SUBMISSION`, Betreiberentscheidung V2, `docs/integrations/ebics.md`).
- Migration `0197_payment_submission`; Regel `docs/rules/M15-01-pain-versions.md`; Runbook
  `docs/runbooks/zahllauf-test.md`; Test `tests/integration/test_m15_payment_submission.py`.

## Lernender Buchhalter: Entscheidungsprotokoll (ADR 0014, rule M12-04, plan M12 S0 and S1)

Ground truth for every later learning step, behind `tenant_settings.learning_bookkeeper_enabled`
(default off; `GET`/`PUT /banking/learning`, accounting:approve plus tenant_settings:update,
reason, event `tenant.learning_bookkeeper_changed`). With the switch off nothing is written and
booking, ignoring and rejecting behave as before. Nothing here posts automatically.

* `features.py`: `collect(session, tx)` assembles the stage 1 input (transaction, approved and
  active rules, open receivables with evidence, open payables) of the ledger of the
  transaction's legal entity; `Features.hash()` is the canonical SHA-256 over it including
  `RULE_VERSION`; `summary()` is the minimised stored form (no names, no purpose, no plain
  IBAN). `posting_proposal.stage1_for_transaction` delegates here; `ENGINE_VERSION` lives in
  `posting_proposal`.
* `proposals.py`: table `posting_decision` (RLS, one pending row per transaction, guard
  trigger `mhvp_posting_decision_guard`: close once, never rewrite, never delete).
  `compute_for_run` (Celery task `mhvp.banking.compute_proposals`, queued after the commit of
  the file and CSV import through `core.db.tenancy.after_commit`, called by the finAPI and
  FinTS tasks after their own commit; inline with `Settings.ai_inline`) snapshots every open
  transaction of a sync run, idempotent per run; a changed `features_hash` expires the old row
  and opens a new round. `record_booking` (called by `_book`) closes the round as
  `accepted_unchanged` or `modified` with the diff of `decisions.py` against the chosen
  proposal (`BookIn.proposal_id`, `chosen`; choosing another proposal is a choice, not a
  modification), `record_rejection` (`POST /transactions/{id}/reject`, reason mandatory,
  transaction stays open, next round opened, optional `ai_proposal_id` closes the AI proposal
  through `mhvp.ai.examples.record_rejection`), `record_ignore` (`POST .../ignore`) and
  `record_reversal` (counter example rows). `POST .../reopen` makes an ignored transaction
  open again with a reason. A stale `proposal_id` is refused with 409 `MHVP-BANK-0021`.
  `GET /transactions/{id}/decisions` lists the rounds (empty while the switch is off: the
  read is gated like the writes, stored rows stay and reappear when switched on);
  `GET .../posting-proposals` names the pending round under `learning`. Tax advisor scope (M18-05) applies to the new endpoints.
* `events_consumer.py`: watermark job (`banking_event_watermark`, beat task
  `mhvp.banking.process_events`, pattern `automation.services.process_tenant`) for
  `journal_entry.reversed` (counter example row, transaction back to `new`, fresh snapshot,
  event `bank_transaction.posting_reversed`), `bank_transaction.reviewed` and
  `contact.deleted` (pending snapshots recomputed). Accounting never imports banking.
* `event_types.py`: names of the bank rule lifecycle events (`bank_rule.proposed`,
  `approved`, `activated`, `disabled`; `superseded` and `downgraded` reserved for S5 and S6)
  and the decision events.
* Reversal reason code: `accounting.services.reverse(..., reason_code=ReversalReason.X)` and
  `journal_entry.reversal_reason_code` (B03); `matching.book_payment` accepts a transaction
  whose effective posting was reversed for exactly one new posting.
* `matching.rule_matches` delegates to `posting_proposal.rule_matches` (one implementation
  plus the legal entity check). Migration 0232. Tests `tests/unit/test_posting_decision_diff.py`,
  `tests/integration/test_m12_posting_decisions.py`. Operator decisions M12-05 to M12-08 in
  `docs/OPEN_QUESTIONS.md`; the data protection review M12-06 blocks the switch in production.

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
* `posting_proposal.py` (27.09.2026, M12-01): deterministic stage 1 of the two stage posting proposal (bank rules, mandate reference, contract or invoice number, purpose determination, payer IBAN, amount) with source, confidence and reasoning per proposal, always active and without AI; `GET /transactions/{id}/posting-proposals` combines it with the stored AI proposals of stage 2 (`ai_posting.py`, tenant switch off by default). Independent set `tests/ai_eval/posting_stage1/cases.json` (200 cases), hit rate per class via `make ai-eval`; rule `docs/rules/M12-01-kontierung-zwei-stufen.md`
* `levels.py`, `verifiers.py`, `runner.py`, `review.py`, `learning.py` (29.09.2026, ADR 0014 addendum, rules M12-05 and M12-06): case classes and automation levels L0 to L3 per tenant with requests released by a second person, deterministic verifiers per class with fingerprint, the runner after every import and sync (advisory lock, G1 open or non leading ledger, case limits, `auto_posted` decisions, review queue due next working day), correction as reversal with reason code plus new posting (`POST /transactions/{id}/correct`), learned rule proposals from repeated identical decisions (thresholds 5 and 3, contradiction withdraws, narrowing only, supersede on activation). Migration 0241; nightly task `mhvp.banking.levels_refresh` (downgrades only)
* `allocation.py`: payer's determination (Tilgungsbestimmung) parsed from the payment purpose (M12-03, D39), deterministic, no AI
* `invoice_matching.py`: invoice to bank transaction matching and draft payment proposal (M11-finapi stage 3, rule M11-06, G2 closed)

## Bank specific CSV import (M11-02, docs/integrations/bank-csv.md)

`csv_formats.py` recognises common German bank CSV exports (Sparkasse, Volksbank/Raiffeisen
Atruvia, DKB, ING, N26, comdirect) from their actual header row only, plus a generic mapping
path for anything else or a header change; only Sparkasse's CAMT-CSV header is verified
against a real sample, the rest is flagged `zu_pruefen` (see the doc for the full list and
`docs/OPEN_QUESTIONS.md` M11-02-csv-header-verification). Encoding (UTF-8/Windows-1252),
delimiter, German decimal comma and several date formats are detected robustly; unreadable
rows are reported, never silently dropped. Output is the same `RawTransaction`/`RawStatement`
shape as CAMT/MT940, so `services.import_file` and its hash based duplicate protection (D05)
apply unchanged. `models.BankCsvMapping` stores a user defined column mapping per account
(migration 0168). Endpoints: `POST /banking/imports/csv/preview` (detected format, rows,
errors, nothing saved), `POST /banking/imports/csv`, `POST`/`GET /banking/csv-mappings`.
Tests: `tests/unit/test_csv_formats.py`.

## Einrichtung in drei Schritten (rule M11-08, 29.09.2026)

The wizard on `/bank` (`apps/web-crm/src/components/banking/BankSetupWizard.tsx`) adds no
banking endpoint: a FinTS account is assigned with `POST /banking/fints/accounts/{id}/assign`
(`property_id`, `legal_entity_id`, `kind`, `holder`), the file path creates the internal
account with `POST /properties/{id}/bank-accounts`; statements are then matched by IBAN
fingerprint as before. The legal entity is derived in the browser from
`GET /properties/{id}/legal-entities` with the same owner table as
`properties.services.ACCOUNT_OWNERS` (6.9.1); the API check stays authoritative. Creditor
contacts from a transaction live in `mhvp.properties.routers_creditors`.

## Payment run, bank limits, status reports (M15-02 to M15-07, S15-02, rule M15-03)

- `payment_run.py`: preview of payable invoices per legal entity (`GET
  /api/v1/accounting/payment-runs/preview`), bulk draft orders with per invoice failures
  (`POST /orders`), payouts without invoice on payable open items (`POST /payout-orders`,
  reasons `owner_payout`, `statement_credit`, `deposit_refund`, `other_refund`), limits per
  ordering account (`PUT /bank-limits/{account}`) enforced before `POST
  /banking/payment-batches` (409), Verification of Payee as a hint only.
- `bank_status.py`: pain.002 and camt.054 import along the public ISO 20022 structure,
  matched by end to end id; status only, never a posting; same file checksum is a no-op.
- `payment_run_tasks.py`: job `mhvp.payments.payment_run`, Monday 08:00, only for tenants
  with `payment_run_setting.weekly_preview_enabled`; stores `payment_run_preview` rows.
- Tables `bank_status_report`, `payment_run_setting`, `payment_run_preview` live in
  `mhvp.accounting.direct_debit_models` (already registered in `mhvp.models`); migration 0253.

## Lückenliste 30.09.2026, Paket P09 (Migration 0258)

- Connector protocol (8.1, M11-03): `BankConnector` has `fetch_balance`, `consent_status` and
  `submit_payment_batch`. Every read connector refuses payment submission
  (`refuse_payment_submission`); payments stay on `payment_submitters` behind G2. finAPI reads
  balances from GET /accounts and the connection status from GET /bankConnections/{id}; the
  consent expiry stays unread until a field is verified (M11-41).
- Sync (8.2, M11-04, M11-05): `finapi_fetch` is one task per account link with three retries
  and exponential backoff (60, 120, 240 s) for provider unavailable or rate limited only.
  `bank_sync_setting.sync_hour` per tenant (default 6); beat `banking-sync-due` (hourly)
  serves tenants with another hour, the 06:00 entries skip them. `POST /banking/sync/run`
  is the manual full sync (generic run plus one fetch task per assigned finAPI account).
- Sync protocol (M11-06): `BankSyncRun.counts` gets `proposals` and `auto_posted` after the
  proposal job (`tasks.record_run_metrics`).
- Allocation (M12-01): unit and property hints are checked against the open item's contract
  (`allocation.location_matches`), in `posting_proposal` and `matching.candidates`.
- Weekly L3 digest (M12-02, rule `docs/rules/M12-S10-wochendigest-l3.md`): `digest.py`,
  table `auto_posting_digest`, beat `banking-weekly-digest` (Monday 05:50), endpoints
  `GET /banking/auto-posting/digests`, `POST .../digests/build`, `POST .../digests/{id}/confirm`.
  The runner blocks the sampled classes at L3 while a digest of an earlier week is unconfirmed.
- Payer IBAN (M12-03): `payer_iban.py`, `GET|POST /banking/transactions/{id}/payer-iban`
  creates a `pending` contact bank account through `contacts.services.add_bank_account`
  (four eyes release by `contacts:approve`).
- AI posting (M12-04, M12-05): `GET /transactions/{id}/ai-posting` returns the run (provider,
  model, prompt version, cost); prompt v2 with up to eight minimised examples of the same
  counterparty only with `ai_learning_examples_enabled` (v1 unchanged otherwise);
  `assert_minimised` checks the example keys; rules accepted from evidence with an AI
  decision carry `learned_from_ai`.
- Test set (M12-06): `tests/fixtures/banking/m12_02_testbestand.json`, 20 synthetic
  transactions with 12 outgoing cases, `tests/unit/test_m12_02_testbestand.py`.


## Package R08 (01.10.2026): property assignment (M2-02/S16-02, Q13-01)

`property_scope.py`: a bank account is visible to a restricted member when its home property or
one of its `bank_account_assignment` properties is assigned. `GET /banking/accounts`,
`/banking/transactions` and `/banking/payment-orders` are filtered; `banking_path_guard` answers
404 for `tx_id`, `transaction_id`, `bank_account_id`, `account_id`, `order_id` and `batch_id`
paths outside the assignment. Rule docs/rules/M2-02-objektzuordnung.md.

## T03 (01.10.2026): Rohdatenablage und Zustimmungserneuerung (M11-07, M11-08)

* `raw_archive.py`: `raw_object_key` bildet `bank/<mandant>/<konto>/<datum>.<ext>`, `archive_raw` legt die unveränderten Bytes dort ab und indiziert sie mit dem Profil `accounting_records` (10 Jahre, Entwurf). Angebunden an den Dateiimport (`/imports`) und den finAPI-Abruf (`FinApiClient.list_transactions(raw_sink=...)`). Regel `docs/rules/M11-07-bankrohdaten-ablage.md`.
* `finapi.parse_consent_valid_until` liest das Ablaufdatum defensiv (Annahme A-M11-08-01) in `complete_connection`, `consent_status` und den Prüfendpunkt. `tasks.remind_consent_expiry` legt zusätzlich eine Aufgabe (Ticket task) an. Regel `docs/rules/M11-08-consent-erneuerung.md`.

## Objektzuordnung (T14, R08-01)

Bankregeln und Regelvorschläge (eigenes Objekt, sonst Objekt des Rechtsträgers), Sync-Protokoll (`GET /banking/runs`) und Klärungsliste (über das Bankkonto des Umsatzes) folgen `Membership.property_ids` (`property_scope.rule_property_filter`, `ensure_rule_visible`, `transaction_account_filter`); fremde Regeln per Id 404. `PUT/DELETE /banking/accounts/{id}/assignments` verlangen ein zugeordnetes Zielobjekt. `account_selection.list_accounts(account_filter=...)` filtert vor dem Limit. Test: `tests/integration/test_t14_property_scope_rest.py`.

### V11 review (01.10.2026)

`parse_amount` refuses ambiguous amounts (more than two decimals, exponent, NaN, infinity);
`build_transactions` reports rows of another own account or another currency as row errors;
`preview` reports a mismatch between the selected account and the file's own account, which
blocks `POST /imports/csv`. Rule: `docs/rules/M11-02-csv-import.md` (Nachtrag V11).
