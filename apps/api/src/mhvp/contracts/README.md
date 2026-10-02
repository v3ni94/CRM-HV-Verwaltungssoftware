# mhvp.contracts

Tenancy and ownership contracts, payments, schedules, SEPA mandates, deposits, versioning and
debtor account reservation.

* Milestone: M5 (docs/MASTER-PROMPT.md section 18), plan and decisions in `docs/plans/M5.md`.
* Specification: docs/MASTER-PROMPT.md 6.3, 6.9.1, 6.9.2, 6.9.11, 7.2, annex A.1, A.3.
* Files: `models.py`, `schemas.py`, `services.py` (creditor entity, debtor accounts, periods,
  plausibility), `validation.py` (SEPA creditor id, mandate reference), `routers.py`.
* Tests: `apps/api/tests/integration/test_m5_contracts.py`, `apps/api/tests/unit/test_m5_rules.py`.
* Locks: no postings (M10, G1), no direct debit collection (G2).

## Sollbeträge im CRM (Paket D, 28.09.2026)

Standing amounts (`contract_payment`: rent, advances, HOA fee, reserve, catalogue
`payment_type`) are recorded and read through the existing endpoints, no new API:

* `POST /contracts/{id}/payments` records a new amount of a kind from `valid_from`; an open
  amount of the same kind that started earlier is closed the day before (`services.add_payment`),
  earlier states are never overwritten. Other overlaps hit the exclusion constraint
  `ex_contract_payment_period` and answer 409; gross must match net and VAT (422); negative
  amounts only for `rent_reduction`; `valid_from` must lie within the term.
* `GET /contracts/{id}/payments` is the history over all versions of the contract number.
* The CRM (`apps/web-crm/src/components/contracts/AmountsPanel.tsx`, helpers `amounts.ts`)
  shows the history with the total per month as of a date, checks overlaps before the request
  and records the first amounts of a new contract from the start date (`ContractForm.tsx`).
* Recording posts nothing: receivables come from the manual receivable run (`mhvp.accounting`),
  statements stay behind G3. The amount has no allocation key and no revenue account in the
  model yet (spec 6.3 names `revenue_account_id`); open point VTR-01 in `docs/OPEN_QUESTIONS.md`.
* Tests: `tests/integration/test_contract_amounts.py` (history, overlap, validation, 403 for
  caretakers, second tenant sees nothing).

## Dienstleisterverträge (M9-06)

`service_contracts.py` (model `ServiceContract`, orientation calculation of next possible end and
latest notice date), `service_contract_routers.py` (`/api/v1/service-contracts`). The notice
date feeds the deadline list (`mhvp.workspace.jobs`, kind `service_contract_notice`, 14 days
lead time). Plan: `docs/plans/M9-06-dienstleistervertraege.md`.

## Performance (Review 26.09.2026)

`GET /contracts`, `/contracts/{id}/versions`, `/sepa-mandates` and `/contracts/{id}/deposits`
build their output with batched helpers (`_outs`, `_mandates_out`, `_deposits_out`: IN lists
instead of one query per row). `GET /contracts` and `GET /sepa-mandates` paginate in the
pattern of `GET /tickets` (`page`, `page_size`, headers `X-Total-Count`, `X-Page`,
`X-Page-Size`; default `limit=200`). Indexes on `contract(tenant_id, end_date |
termination_date | kind)` and `sepa_mandate(tenant_id, status)` (migration 0127). See
`docs/reviews/2026-09-26-performance.md`.

## Kautionsabrechnung (M5-02, operator decision 26.09.2026)

`deposit_settlement.py` (models `DepositInterestReferenceRate`, `DepositSettlement`, pure
`Decimal` computation: day exact interest per calendar year on the balance basis, rounded once
per year), `deposit_settlement_routers.py` (`/deposit-interest-rates`, `/deposits/{id}/settlements`,
`/deposit-settlements/{id}/release` behind G3). Migration 0138. Rule and hand computed example:
`docs/rules/M5-02-kautionsabrechnung.md`. Tests: `tests/unit/test_m5_deposit_settlement.py`,
`tests/integration/test_m5_deposit_settlement.py`. The settlement is a record only; no
posting, no payment, no receivable.
## Freigabe der Importverträge (Betreiberauftrag 26.09.2026)

Verträge aus der Immoware24 Zuordnung (`mhvp.imports.zuordnung`) haben einen angenommenen
Vertragsbeginn und übernommene Beträge. Sie müssen vor der ersten Sollstellung durch die
Geschäftsführung freigegeben werden.

* Felder am Vertrag (Migration 0146): `source` (z. B. `immoware24:zuordnung`, leer bei manueller
  Anlage), `approval_status` (`pending`, `approved`, `rejected`; Standard `approved` für Bestand
  und manuell angelegte Verträge), `approved_by`, `approved_at` (Entscheidung, auch bei
  Ablehnung). Die Zuordnung setzt `source = immoware24:zuordnung` und `pending`. Bereits vor der
  Migration importierte Verträge bleiben `approved`.
* Sollstellung: Es gibt keinen automatischen Sollstellungslauf, der Lauf wird manuell über
  `POST /accounting/receivable-runs` (Vorschau) und `.../post` gestartet. `receivables.compute`
  liest nur Verträge mit `approved`; die Vorschau zählt übersprungene ausstehende Verträge in
  `totals.skipped_pending_approval`, die CRM-Ansicht zeigt den Hinweis. Eine Freigabe nach der
  Vorschau ändert die Grundlage, die alte Vorschau wird beim Buchen abgewiesen (409).
* API: `GET /contracts/pending-approval` (Filter `source`, `property_id`, `kind`; Objekt,
  Einheit, Partei, Art, Beginn, Monatsbetrag als Summe der am Beginn gültigen Zahlungen, Quelle),
  `POST /contracts/approve` mit `{ids}` oder `{all: true, source?}`, je Vertrag Ereignis
  `contract.approved` mit Nutzer und Zeit; wiederholte Freigabe ohne Wirkung.
  `POST /contracts/{id}/reject-import` beendet einen ausstehenden Vertrag zum Beginn
  (`end_date = start_date`, Zahlungen und Zahlungspläne ebenso), markiert ihn `rejected` und
  schreibt `contract.import_rejected`. Freigeben und Ablehnen verlangen `contracts:approve`
  (nur `tenant_admin` und `administrator`), die Liste `contracts:read`.
* CRM: Seite `/vertraege/freigabe` (Link auf der Vertragsliste) mit Filtern Quelle, Objekt,
  Art, Summen je Art, Mehrfachauswahl, "Ausgewählte freigeben", "Alle freigeben" mit
  Bestätigung und Hinweis auf die Annahme des Vertragsbeginns, "Ablehnen" je Zeile. Kennzeichen
  "Freigabe ausstehend" in Vertragsliste und Vertragsdetail; die Einheitenansicht listet keine
  Verträge, dort gibt es daher kein Kennzeichen.
* Tests: `tests/integration/test_contract_import_approval.py`,
  `tests/integration/test_zuordnung_import.py`,
  `apps/web-crm/src/components/contracts/ContractApprovalPanel.test.tsx`.

## P1 Ergänzungen zum Vertrag (Ergänzung CRM 4.5, AP3, Migration 0150)

Datensätze und Anzeige, keine Buchungen; G1 bis G3 bleiben geschlossen.

* Felder (Migration 0150): `contract.move_in_on`, `contract.move_out_on` (Kalendertermine Einzug
  und Auszug, unabhängig von Beginn und Ende; Auszug nie vor Einzug),
  `sepa_mandate.payment_type_codes` (Liste aus Katalog `payment_type`, leer = alle Ertragsarten,
  unbekannte Codes werden abgewiesen) und `sepa_mandate.exclude_special_levy`. Tabellen
  `contract_allocation_value` (Umlageschlüssel des Objekts, Wert, Zeitraum; Zeiträume je Vertrag
  und Schlüssel überschneiden sich nie, Beginn innerhalb der Laufzeit) und
  `contract_termination_reading` (Zähler, Wert, Datum, Verweis auf den erzeugten
  `meter_reading`), beide mit RLS.
* API: `GET`/`POST /contracts/{id}/allocation-values` (die Liste umfasst alle Versionen der
  Vertragsnummer; ein neuer Wert schließt den offenen Vorwert desselben Schlüssels am Vortag,
  Überschneidung mit geschlossenen Zeiträumen ist 409). `POST /contracts/{id}/termination`
  nimmt zusätzlich `move_out_on` und `meter_readings` (Zähler der Einheit oder Gemeinschaftszähler
  des Objekts; je Zähler ein Stand, Datum Standard Vertragsende) und schreibt je Eintrag einen
  `meter_reading` (Quelle `manual`) plus Verknüpfung; `GET /contracts/{id}/termination-readings`
  liest sie. `GET /contracts?status=active|ended|upcoming&as_of=` (Standard heute).
  `GET /deposits` (Kautionsliste über alle Verträge mit Objekt, Einheit, Partei, Sollbetrag,
  erhalten, Guthaben, offen; Filter `property_id`, `status`, `outstanding_only`).
  `GET /properties/{id}/vacancies?as_of=` (vermietbare Einheiten ohne Mietverhältnis mit
  Leerstandsbeginn und letztem Mietvertrag). Rechte wie bisher: Lesen `contracts:read`,
  Erfassen `contracts:update`, Mandate `contracts:create`.
* CRM: Vertragsseite mit Abschnitten Eigenschaften (Umlagewerte mit Erfassung), SEPA-Mandate
  (Standard- und Zusatzmandate mit Ertragsarten und Sonderumlage-Ausschluss), Debitorenkonto
  (Nummer, Name, Sprung in den Buchungskreis des Gläubigers unter `/buchhaltung/[id]` für Saldo
  und offene Posten, Einzug und Auszug, Zählerstände der Beendigung). Beenden im
  Bearbeitungsformular mit Auszugsdatum und Zählerständen je Zähler der Einheit.
* Tests: `tests/integration/test_contracts_p1.py` (Happy Path, Validierung, Rechte,
  Mandantentrennung), `apps/web-crm/src/components/contracts/ContractAllocationValues.test.tsx`.

## Inline editing (Ergänzung CRM AP8, ADR 0012, 27.09.2026)

`PATCH /contracts/{id}/notes` (`ContractNotesPatch`) changes `notes`, `dunning_block` and
`dunning_block_reason` in place without a new contract version (operator decision (c) 4,
option a); a block needs a reason (422). Payments, terms and parties keep the version path.

## Vertragsliste mit Zuordnung und Suche (Rückmeldung 28.09.2026)

* `GET /contracts` liefert je Zeile zusätzlich `property_number`, `property_name`,
  `property_address`, `unit_number`, `unit_label`, `party_name` und `members` (Kontakte der
  Vertragspartei mit `contact_id`, Name, Rolle), in vier gebündelten Abfragen je Seite.
* `q` (max. 200 Zeichen): Freitextsuche, jedes Wort muss treffen in Vertragsnummer,
  Parteiname, Kontaktname (Anzeigename, Vorname, Nachname, Firma), Objektnummer, Objektname,
  Straße, PLZ, Ort, Einheitsnummer oder Einheitsbezeichnung. `ILIKE` auf einfachen Spalten in
  Unterabfragen, jede unter der Mandanten-RLS; `%` und `_` werden maskiert. Kein zusätzlicher
  Index: EXPLAIN als `mhvp_app` zeigt je Tabelle den Mandantenindex als Index Cond und das
  `ILIKE` als Filter (Teilwortsuche ist ohne Trigramm-Index nicht indexierbar, der Bestand je
  Mandant ist klein). Bestehende Filter und Paginierung bleiben unverändert.
* CRM `/vertraege`: Suchfeld (GET-Formular, Filter Objekt und Einheit bleiben erhalten),
  Spalten Objekt (Link `/objekte/{id}`, Anschrift), Einheit (Link `/vermietung/einheit/{id}`)
  und Mieter oder Eigentümer (Links `/kontakte/{id}`).

## Eigentümerwechsel mit Übernahme der Sollbeträge (operator 28.09.2026)

`GET /contracts/{id}/ownership-transfer/preview?title_transfer_date=` (`contracts:read`, read
only) shows what the transfer would do: the current ownership ends the day before, the new one
starts on the date, and the standing amounts valid on the date (`services.standing_amounts`:
payments, payment schedule, contract allocation values) are listed. `POST
/contracts/{id}/ownership-transfer` takes the acquirer as `new_party_id` or `new_contact_id`
(`mhvp.contacts.services.party_for_contact`: the contact's own single member party, created
when missing), `carry_over_amounts` (default true: `services.carry_over_standing_amounts`
copies the rows with `valid_from` = title transfer date and the original `valid_to`), `notes`
and `document_id` (linked as `evidence` to the new contract). Allocation values of the old
contract end the day before (`services.close_allocation_values`). Error code `MHVP-CONTR-0001`
for a contract that cannot be transferred. The carry over is a factual copy: no split of the
annual statement between seller and acquirer (rule W07 not released, release point P01 open),
no posting, open receivables stay with the seller (6.9.2, D15). Rule
`docs/rules/M5-03-eigentuemerwechsel-sollbetraege.md`, tests
`tests/integration/test_ownership_transfer.py`, web `OwnershipTransfer.tsx` on the contract
and the unit page.

## P16 follow-up maintenance (wave 2)

`routers_p16.py`: `PATCH /contracts/{id}/custom-fields`, `PATCH /contracts/{id}/payments/{id}` and
`PATCH /contracts/{id}/schedules/{id}` (locked for amounts, period and type once a posted receivable
item refers to the row, 409), `PATCH /deposits/{id}` (status model open, active, settled; documents).
`mandates.py` and job `mhvp.contracts.expire_mandates`: expiry by `valid_until`, usage bookkeeping
for the collection after G2. New columns in migration 0265: `contract.custom_fields`,
`contract_payment.revenue_account_id`, `deposit.documents`. Rule: `docs/rules/P16-stammdaten-pflege.md`.

## R10 Kautionsverzinsung (B15)

`deposit_settlement.py` / `deposit_settlement_routers.py`: Zinssatzverlauf je Kautionskonto (`deposit_interest_rate`, `GET/PUT/DELETE /deposits/{id}/interest-rates[/{valid_from}]`), Jahresgutschrift als Entwurf (`deposit_interest_draft`, `POST/GET /deposits/{id}/interest-drafts`, `POST /deposit-interest-drafts/run|{id}/confirm|{id}/discard`) und Zinsart `deposit_rates` der Kautionsabrechnung (`interest_by_rate_history`). Bestätigung erfasst nur eine Zinsbewegung, keine Buchung. Migration 0288. Regel: `docs/rules/R10.md`.

## AE17 Umlagevereinbarungen

`allocation_routers.py`: `allocation_agreement` je Mietvertrag und Betriebskostenart mit Klauselbezug, Dokument und Gültigkeit (keine Überlappung), CRUD unter `/contracts/{id}/allocation-agreements`, Massenerfassung `POST /properties/{id}/allocation-agreements/bulk` (Vorschau als Standard, kein Überschreiben). Regel `docs/rules/AE17-01.md`.

## Settlement PDF preview (GAG-29)

`GET /contracts/{id}/deposit-settlements/{settlement_id}/document-preview` (`contracts:read`) renders the stored settlement draft as PDF without filing, sending or posting (`Cache-Control: no-store`). CRM: `DepositSettlementPreviewButton` in `DepositPanel` (BFF allowlist entry). Tests: `tests/integration/test_ah18_deposit_settlement_preview.py` (read permission, 403 without role, foreign tenant 404, unknown or mismatching ids 404, 422).

### Deposit hint (AI18, GAH-111)

`DepositHintSetting` (default off) adds non blocking `limit_hints` to `DepositOut` for residential tenancies; `GET/PUT /deposit-hint-settings` with `tenant_settings` permissions. Rule AI18-02.
