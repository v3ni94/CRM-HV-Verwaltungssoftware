# mhvp.hoa

Owners' meetings, resolutions, board audits (audit_engagement).

* Milestone: M25 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.5, 6.9.12, 7.8 W13, 7.9.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/hoa/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Implemented parts (M24, M25; see docs/plans/M24.md, M25.md)

* `models.py`, `calc.py`, `routers.py`: economic plan, resolutions, annual statement.
* `package.py`: statement package and blocking checks (W12), including the W03 partial scope
  check (D18) and the resolution validity block (D54).
* `levies.py`: special levies with instalments, amendments and earmarked report (W09, D20).
* `meetings.py`: owners' meeting, circular resolutions, board audit (M25).
  Circular resolutions (M25-02): unanimous in text form by default; a simple majority only
  with the tenant switch `hoa_circular_lower_majority_enabled` (default off), a prior
  admitting resolution of the community, a voting deadline and the tenant's majority rule for
  the subject kind (`docs/rules/M25-02-umlaufbeschluss.md`, legal review open).
* `meeting_rules.py`: invitation period per tenant (latest dispatch date, short notice only
  with a documented reason noted in the minutes, calendar source "Einladung spätestens"),
  virtual form behind the tenant switch with enabling resolution and validity end, dial-in
  data (encrypted, owners in the portal only), attendance list with channel (M25-03, V13,
  `docs/rules/M25-03-einladung-virtuell.md`, migration 0187).
* `protocol.py`: minutes draft of a meeting from a placeholder template as PDF on the tenant
  letterhead (A62); a draft without legal effect, the signed minutes stay linked separately.
* Reserve block of the statement: Soll, Ist, open contributions, bank balance and explained
  difference, never a settlement entry (W08, D19).
* `board.py`: board access per audit engagement, revocation and the management answer to a
  board question (A52, docs/rules/M21-07.md); the board itself works in `mhvp.portal.board`.
  A72: candidate bookings for audit items (`GET /hoa/audits/{id}/candidates`, filters account,
  vendor, date, text; the selection stays `POST /hoa/audits/{id}/items`), the list of reports
  (`GET /hoa/audits/{id}/reports`) and the board statement on a report
  (`POST /hoa/audit-reports/{id}/board-statement`, text only in `content.board_statement`
  with history, no release effect, no schema change).
* `finance.py`: loans, insurance claims and larger measures (W10, A59); items count only with
  a posted journal entry, documents via DocumentLink, no posting. `GET /hoa/loans/{id}/schedule`
  (A78): annuity or linear plan from `calc.loan_schedule` with the comparison against the booked
  items per month, orientation only. Claims carry a checked `resolution_id` (A79, migration 0128).
* `calc.cash_flow_reconciliation`: Gesamtgeldfluss and Überleitung of the statement year (W04,
  A60); an unexplained difference blocks the package. Takeover year (A80, 6.9.10): the posted
  opening balance entries of the year give the opening balance and the explained difference
  `migration_opening` (block `migration`).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `inspection.py`: inspection requests outside the portal with history and deterministic provision package (A61, rule A61); router registered in `main.py`
* `majority.py`: majority rules per subject kind and automatic check on a resolution, no status change (M25-01, rule M25-01, migration 0125); router registered in `main.py`

## Addendum 27.09.2026 (M24-02, M24-03)

* `assets.py`: asset report per reporting date (W11, rule M24-02): `hoa_asset_report` (migration
  0171, RLS), endpoints `/hoa/asset-reports` (create, list, get, patch, calculate, transition
  `issued` behind G4, PDF draft on the tenant letterhead with watermark). Blocks: reserve Soll and
  Ist, bank per account, receivables per unit, payables and owner credits, loans with residual
  debt, manual items; reconciliation against the ledger with visible differences, never settled.
  `GET /hoa/loans/{id}/annual?year=`: interest, repayment and residual debt of a year
  (`calc.loan_year_figures`, booked items or schedule as orientation).
* `routers.py`: `PUT /hoa/statements/{id}/loan-allocation` (draft only, key and basis required,
  column `hoa_statement.loan_allocation`); `calculate` adds the block `loans` and the per unit
  shares `loan_interest_share` and `loan_repayment_share` (rule M24-03, information only, the
  result stays unchanged). Tests: `tests/integration/test_m24_asset_report.py`.

## Addendum 29.09.2026 (W02 takeover, M12 gaps)

* `routers.py`: `GET /hoa/plans/{id}/apply/preview` and `POST /hoa/plans/{id}/apply` with
  `confirm` and `snapshot_hash`: standing amounts per ownership contract from `valid_from`,
  second person (not the plan's creator), idempotent, posted months counted and never charged
  again. Rule `docs/rules/W02-wirtschaftsplan.md`; the rows are contract master data, the
  receivable run behind G1 reads them. Test: `tests/integration/test_m12_letters_plan_export.py`.


## Prüfung und Einsicht, Erweiterung P08 (30.09.2026)

* `GET /hoa/audits/{id}` mit Filtern `min_amount`, `max_amount`, `missing_document`, `has_risk`, `item_status`; Prüfauftrag mit `authorization_text` und `data_as_of`.
* `PATCH /hoa/audit-items/{id}` mit `risk_note`; Verlauf `GET /hoa/audit-items/{id}/history` (Tabelle `audit_item_event`).
* `POST /hoa/audits/{id}/reports/{version}/confirm`: einmalige Bestätigung einer Berichtsversion, kein Beschluss.
* Einsichtspaket mit `valid_days`, Widerruf `POST /hoa/inspection-requests/{id}/revoke`, danach 409 beim Abruf.
* Regel `docs/rules/P08-pruefung-einsicht.md`, Migration 0257.

## Addendum 30.09.2026 (P07, M24-01 to M24-07)

* Earmarked reserves `hoa_reserve` and movements `hoa_reserve_movement` (withdrawal, tax, fee,
  interest with receipt or entry); `POST/GET /hoa/reserves`,
  `POST /hoa/statements/{id}/reserve-movements`; snapshot `reserve.positions`.
* `POST /hoa/statements/{id}/costs/from-ledger`: one cost position per posted entry of an
  account in the year, linked to entry and receipt; package shows `receipt_status`,
  `payment` drilldown and `missing_receipts`.
* Cost items: `journal_entry_id`, `document_id`, `labour_cost_35a`, `basis_resolution_id`,
  `basis_document_id` (structured W03 source replaces the term check).
* Snapshot blocks `key_figures` (with debtors) and `section_35a`.
* Plan master data (title, as_of_date, basis_statement_id, basis_plan_id, payment_rhythm,
  due_day, continues_until_new_plan, obsolete_at) and `comparison` in the plan snapshot.
* `GET /hoa/statements/{id}/units/{unit_id}/pdf`: unit statement PDF draft (G4, after approval).
* Migration 0256. Rule: `docs/rules/M24-W2-abrechnung-plan.md`.

## Wave 3, package Q09 (30.09.2026)

* Reserve binding (M24-01, migration 0278): `contract_payment.reserve_id` and
  `receivable_item.reserve_id` (earmark of the standing amount, carried into the receivable
  item). `plan_results` adds `reserve_split` per unit; `apply_plan` binds a unit's reserve
  advance only when it goes to exactly one reserve. The statement sums payments per reserve
  (`reserve.contributions_paid_by_reserve`, `contributions_paid_unassigned`); `positions` carry
  `contributions_paid`, `contributions_paid_bound` and `paid_change`.
* Rhythm (P07-03): a quarterly or yearly plan creates a payment schedule per contract on apply
  (`_ensure_schedule`, advance, amount per month, due day of the plan); response field
  `schedules_set`; preview rows carry `rhythm` and `instalment`.
* `GET /hoa/statements/{id}/pdf`: Gesamtabrechnung on the tenant letterhead (G4, after
  approval, `statement_pdf.build_total_letter`).
* `totals_comparison` in the plan snapshot (previous plan or previous statement).
* Inspection: event kinds `notified` and `owner_check`, `POST /hoa/inspection-requests/{id}/owner-check`.
* Reports list returns `confirmed_by_name`, `confirmed_at`, `confirmation_note`.
* `statement_kind` accepts `special_levy` and `heating` (accounting enum, SA-08).
* Rules: `docs/rules/M24-W3-ruecklage-rhythmus.md`, `docs/rules/M25-W3-einsicht-pruefrolle.md`.
* Inspection (R05, migration 0287): `PackageIn.valid_days` falls back to `tenant_settings.inspection_package_default_days` (empty: no expiry); `no_expiry=true` overrides a set default for one package. Rule P08-06.


## Package R08 (01.10.2026): property assignment (M2-02/S16-02, Q13-01)

`property_scope.py` (`HOA_GUARD`, `HOA_BOARD_GUARD`): WEG ids in path or query (statement, plan,
meeting, resolution, levy, loan, measure, claim, engagement, audit, asset report, legal entity,
ledger) resolve to the property; outside the membership assignment 404. Inspection requests
are guarded in `inspection.py` and their list is filtered. Audit reports of the board carry no
legal entity and are not guarded by id.

## Addendum 01.10.2026 (T09, M24-01 reserve per position)

* `hoa/reserves.py`: `GET/PATCH /hoa/reserves/{id}` (bank account of the ledger's legal
  entity, opening balance and year, legal entity in the output), `GET /hoa/reserves/{id}/development?year=`
  (opening, contribution, withdrawals, taxes, fees, interest, closing per year, chained),
  `GET /hoa/statements/{id}/reserve-movements`, `DELETE .../reserve-movements/{mid}` (draft only).
* Statement snapshot positions carry `opening`, `closing_planned`, `closing_paid`; the asset
  report reserve block carries `positions`. Migration 0294. Nothing posts (rule M24-W5).

* Property assignment (T14, R08-01): `board._engagement` also resolves the property of the community, so audit reports by id (`/hoa/audit-reports/{report_id}/...`) and all engagement paths answer 404 outside `Membership.property_ids`.

## Reserve statement (S69-01, wave 5)

`reserve_statement.py`: own statement object per ledger and year (`/hoa/reserve-statements`,
table `reserve_statement`, migration 0295) with the shared status model; created from the
reserve block of the calculated Hausgeldabrechnung and the reserve master data (migration
0294); issued, due and posted behind G4. Rule: `docs/rules/S69-01-statement-status-model.md`.


CRM (U03, 01.10.2026): Das Rücklagenformular bietet Bankkonto (nur Rechtsträger der Gemeinschaft) und Buchungskonto als Auswahl; die Hausgeldabrechnungsansicht zeigt die Entwicklung je Rücklage und Jahr (`GET /hoa/reserves/{id}/development`). Keine API-Änderung.

## Closing of the minutes (R07-01, wave 7, V05)

`POST /hoa/meetings/{id}/close` (status `held` only, `minutes_document_id` required) sets
status `closing` and locks agenda, attendance, votes, announcements, disruptions and the
deadline patch (409). A second person confirms with `POST .../close/confirm` and the same
document: status `closed`, event `meeting.closed` (webhook catalogue). `POST .../close/withdraw`
returns an open request to `held`. No statutory minutes period is computed (open question
V05-01); the response carries a hint text only. Migration 0302, rule `docs/rules/R07-01-meeting-close.md`.

## Reserve opening lock and reference checks (U15-03, V11-06, wave 7, V01)

Opening balance and year are frozen once a statement of the opening year is calculated or
beyond (409 `MHVP-HOA-0005`); ended bank accounts and inactive ledger accounts are refused
with 422. Rule M24-W5 addendum.

## Review W79 (01.10.2026)

`HOA_GUARD` and `HOA_BOARD_GUARD` now combine the property assignment guard with a legal entity
scope guard (A37): a `legal_entity_id` parameter or the id of a WEG record with a legal entity
outside `Membership.legal_entity_ids` answers 404. The reserve opening lock covers statements from
the earlier opening year on; the minutes document of the closing is scope checked and must not
belong to another community. See `docs/reviews/REVIEW-W79-2026-10-01.md`.

## Vermögensbericht im Portal und Sondererwerb (AA07, 01.10.2026)

* GA07-02: `portal/owner_assets.py` (`/portal/owner/asset-reports`, PDF hinter G4) schreibt je Abruf eine Zeile pro Eigentumsvertrag nach `hoa_asset_report_provision` (Migration 0309); `GET /hoa/asset-reports/{id}/provisions` zeigt das Protokoll. Das PDF rendert `assets.render_report_pdf`.
* GA07-03: `acquisition.py` erzeugt im Abrechnungspaket den Befund `acquisition_unreleased` für Sondererwerbe; Antrag und Freigabe durch eine zweite Person (`hoa_acquisition_release`, MHVP-HOA-0020). Zuordnungsvorschlag nur als Text, Regel offen (AA07-01).

## Meeting kinds, agenda results, vote channel, Beschluss-Sammlung (AA06, 01.10.2026)

Migration 0308. Rules: `docs/rules/AA06-versammlung-beschluss-sammlung.md`.

* `owners_meeting.kind` also accepts `repeat`, `continuation` (both need `origin_meeting_id`,
  an earlier meeting of the same community), `partial` and `circular_resolution`. New fields
  `ends_at` (after `scheduled_at`), `invitation_template_id`, `proxy_template_id`,
  `ballot_template_id` (`document_template`, SET NULL), `public_description` (owner portal)
  and `internal_description` (CRM only). `PATCH /hoa/meetings/{id}` edits them.
* Agenda item: `majority` `all_owners` (tally checks yes votes of all owners entitled to vote
  on the meeting day, not only those present), `voting_principle` with
  `voting_principle_basis` (precedence over the meeting), `result` (`accepted`/`rejected` set
  by the announcement, `deferred`/`no_vote` via `PATCH /hoa/agenda/{id}`, which blocks votes
  and announcement) and `minutes_text` (protocol draft).
* `meeting_vote.channel`: `online` or `presence` from the attendance; `circular` only in a
  meeting of kind `circular_resolution` (owner of the community, no attendance needed). Tally
  returns `channels`, members list `vote_channels`.
* `resolution`: `location`, `court_notes`, `entered_at` (time of entry, backfilled from
  `created_at`). Status also `deleted` and `irrelevant` (notes, no physical deletion); `void`
  remains accepted until the operator decides (AA06-01). `PATCH /hoa/resolutions/{id}` takes
  `status`, `court_notes`, `location` (each change emits an event).
* GA07-01: `meeting_rules.basis_term_notice`: validity end of the enabling resolution later
  than decision date plus three years gives `virtual_basis_term_notice` on creation; lock
  `MHVP-HOA-0030` only with `tenant_settings.hoa_virtual_basis_term_lock_enabled` (default
  off, `PUT /hoa/meeting-settings` field `virtual_basis_term_lock_enabled`). Transition rule
  § 48 Abs. 6 WEG not implemented (AA06-02).
