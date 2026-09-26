# mhvp.contracts

Tenancy and ownership contracts, payments, schedules, SEPA mandates, deposits, versioning and
debtor account reservation.

* Milestone: M5 (docs/MASTER-PROMPT.md section 18), plan and decisions in `docs/plans/M5.md`.
* Specification: docs/MASTER-PROMPT.md 6.3, 6.9.1, 6.9.2, 6.9.11, 7.2, annex A.1, A.3.
* Files: `models.py`, `schemas.py`, `services.py` (creditor entity, debtor accounts, periods,
  plausibility), `validation.py` (SEPA creditor id, mandate reference), `routers.py`.
* Tests: `apps/api/tests/integration/test_m5_contracts.py`, `apps/api/tests/unit/test_m5_rules.py`.
* Locks: no postings (M10, G1), no direct debit collection (G2).

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
