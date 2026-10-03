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

## Follow-up AB06 (01.10.2026, migration 0325 noop)

* GA03-01: the CRM creation form offers `repeat` and `continuation` with a selection of earlier
  meetings of the same community (`origin_meeting_id`); templates for invitation, proxy and
  ballot are chosen from `GET /document-templates` instead of typing an ID. The owner portal
  shows `public_description` (the internal description never leaves the API for the portal).
* GA07-01: `GET /hoa/meetings/{id}` returns `virtual_basis_term_notice` permanently (same text
  as on creation); the CRM detail view shows it. The lock `MHVP-HOA-0030` stays behind the
  tenant switch (default off), decision AA06-02 open.
* GA03-03 stays partial: `void` unchanged until AA06-01 is decided.

### Problem code assignment (HOA)

Codes `MHVP-HOA-0006` to `MHVP-HOA-0019` are unassigned and stay free; they are not reused
for renumbering. Assigned: 0001 to 0005 (M24/M25 base), 0020 (GA07-03 four eyes), 0030
(GA07-01 term lock). Rule: a new code takes the next number above the highest assigned one of its package group
(parallel packages reserve their own number; gaps are allowed); existing codes are never
renumbered or reassigned (ADR 0004, codes are part of the API contract). Register
every new code in `mhvp.core.problems` at the end of the HOA block and in the rule file.

## Follow-up AB07 (01.10.2026, migration 0326 noop)

- `POST /hoa/asset-reports/{id}/dispatch` (accounting:create, G4, status `issued`): one letter per resolved recipient of each ownership contract on the reporting date, filed as generated document (`generated_document.context_type = hoa_asset_report`) and handed to `mhvp.communication.dispatch` (channel of the request, else contact preference, else tenant default). Default only owners without portal retrieval; contracts with an existing letter are skipped. The provision log lists `dispatches` per contract.
- `acquisition.py`: German case labels (`case_label`, findings) for first acquisition, forced sale and special succession; tests for these cases. No allocation rule (AA07-01), `calc.py` unchanged.

## Online meeting in the owner portal (AD06, GA11-03)

`online_meeting.py` (CRM) and `mhvp.portal.owner_meetings` (portal). Per tenant switch
`hoa_online_meeting_setting.enabled` (default off, `GET/PUT /hoa/online-meeting-settings`,
403 MHVP-HOA-0031). CRM: `POST /hoa/meetings/{id}/agenda/{item}/voting/open|close`,
`POST /hoa/meetings/{id}/speaker-requests/{rid}`, `GET /hoa/meetings/{id}/online`. Portal:
`GET /portal/meetings/{id}`, `POST .../participation`, `POST .../speaker-requests`,
`GET/POST /portal/meeting-proxies`, `POST /portal/meeting-proxies/{id}/revoke`,
`POST /portal/meetings/{id}/agenda/{item}/votes` (G4, channel online, one per unit, 409 when
the item is not open). Migration 0351. Rule: `docs/rules/AD06-online-versammlung.md`.

## Korrekturbericht (AE11, P02, D09)

`POST /hoa/statements/{id}/new-version` nimmt optional Grund (resolution_changed, court_invalid, calculation_error, other), Bezug und Beschluss entgegen und übernimmt Kostenpositionen mit Belegen, Abstimmungsnotizen und Darlehensangaben. `GET /hoa/statements/{id}/correction-report?against=<ältere Version>` liefert Einheitsdiff, Differenz je Eigentümer (`correction.py`) und den Heizkostenblock; keine Buchung, Rechtsfolge offen. Regel: docs/rules/P02-korrekturbericht.md.

## AE12: Übergangsstichtag und Fristhinweise (virtuelle Versammlung)

`PUT /hoa/meeting-settings` nimmt optional `virtual_basis_transition_date` (Weglassen behält, `null` löscht); das Datum hat keine Sperrwirkung. `GET /hoa/meetings/{id}` liefert `virtual_basis_deadlines` (Orientierung, zu verifizieren). Schalter `hoa_virtual_meetings_enabled`, `hoa_virtual_basis_term_lock_enabled` und `hoa_online_meeting_setting.enabled` bleiben Standard aus. Migration 0368.

## Payments per earmarked reserve (AE08, P07-02, rule AE08-01)

`contract_payment.reserve_id` is now accepted on `POST /contracts/{id}/payments` (active reserve of the
property's GdWE). `hoa_reserve_payment_setting.mode` (migration 0364, default `bound_only`) selects the
variant; `plan_ratio_proposal` adds `contributions_paid_proposal` per statement position and
`paid_proposal` in `GET /hoa/ledgers/{ledger_id}/reserve-payments?year=` (`hoa/reserve_split.py`).
Proposal only: nothing is posted, items and the statement basis stay unchanged, G4 stays closed.

## Plan change within the year (AE09, M24-08, P07-01, rule AE09-01)

`hoa/plan_change.py`: difference of months already posted from `valid_from` (new monthly amount
minus posted receivables per unit, component and month). Tenant switch
`hoa_plan_change_setting.mode` (`notice` default, `due_now`, `next_instalment`, migration 0365).
Drafts in `hoa_plan_difference`; approval needs G4 and a second person; nothing is posted (G1).
The apply preview carries `plan_change_mode` and `differences_total`.

## AE10: Zuordnungsregel bei Eigentümerwechsel (AA07-01, Migration 0366)

`hoa/acquisition_rule.py`: Mandantenregel je Erwerbsart in `hoa_acquisition_rule`
(`manual_release` Standard, `by_due_date`, `by_resolution_date`; keine Zeile gleich Standard).
`GET /hoa/acquisition-rules` (accounting:read), `PUT /hoa/acquisition-rules/{kind}`
(accounting:approve). Hook `calc.allocation_owner`: bei Standard exakt `owner_at(default_day)`,
die Berechnung bleibt unverändert; angewendet auf den Schuldnervorschlag der Differenz einer
Sonderumlage (`levies.py`). Die Freigabeliste der Sondererwerbe zeigt die Variante. Die
Rechtsfrage je Erwerbsart bleibt offen (AA07-01, P01), G4 bleibt geschlossen.

## AE07: reserve plan per year and opening switch (M24-01, V01-01, rule AE07-01)

`hoa/reserve_plan.py`, migration 0363. `hoa_reserve_plan` holds the planned contribution per
reserve and year with economic plan and resolution reference (draft, resolved, superseded;
resolved needs a resolution and is frozen). `POST /hoa/plans/{id}/reserve-plans/derive` builds
drafts from the reserve items. The development takes a resolved reserve plan as Soll
(`planned_source`). `hoa_reserve_policy.opening_lock_mode` (default `locked`) decides how
opening changes after a calculated statement are handled: 409, logged change or four eyes
request (`/hoa/reserve-opening-changes/{id}/approve|reject`). Tax classification is a
placeholder (`not_released`). Nothing is posted.

## AE31: proxy against own vote, online data in the minutes draft, checklist (AD06-01 to AD06-03)

`hoa/online_rules.py` (pure rules), `hoa/online_meeting.py`, `hoa/protocol.py`, migration 0387.
Rule document: `docs/rules/AE31-online-stimmen-vollmacht.md`. Nothing legal is decided.

* `hoa_online_meeting_setting.proxy_conflict_mode` is the tenant rule for a unit that receives a
  vote of the owner and a vote of the proxy holder: `flag` (default: the first vote stays
  counted, the second is stored in `meeting_vote_conflict` for review, nothing is discarded),
  `first_vote` (second refused, 409), `proxy_priority` and `own_priority` (the preferred source
  replaces the other vote, the replaced vote stays in the conflict record). The same source
  twice is always 409. The rule applies to the portal vote (`portal/owner_meetings.py`) and to
  the CRM vote (`POST /hoa/agenda/{id}/votes`) through `online_meeting.handle_second_vote`.
  `meeting_vote.cast_source` and `meeting_vote.proxy_id` record the source of a vote.
* `POST /hoa/meetings/{id}/vote-conflicts/{conflict_id}/resolve` (`accounting:create`): the meeting
  chair confirms the first vote (`keep_first`) or counts the second (`apply_second`, only before
  the announcement). Both choices stay in the record; the tally calculation is unchanged.
* `GET /hoa/meetings/{id}/online` also returns `proxy_conflict_mode`, `vote_conflicts`,
  `open_conflicts` per item and `admissibility`: a checklist of recorded facts (switches,
  enabling resolution with status and validity end, three year note, conference link). It
  states no legal rule; the note names the open question AD06-01.
* The minutes draft (`protocol.online_context`) adds, for hybrid or virtual meetings or when
  portal data exist, the section "Online-Teilnahme" (confirmations, portal proxies, requests to
  speak with time, unit and note, checklist), per item the online votes (with proxy share) and
  the review notes on vote conflicts, and open conflicts in the draft notice. A presence meeting
  without portal data renders exactly as before.

## AF08 (wave 17): GAA-02, GAE-11 to GAE-14 (migration 0402)

* `hoa/inspection_transfer.py`: consumer of `contract.ownership_transferred`. Open inspection
  requests of the previous owner side get an `owner_check` note with `source_event_id` (unique
  per request and event); nothing is closed or revoked (P08-02). Hourly beat
  `hoa-inspection-ownership-scan` and `POST /hoa/inspection-requests/ownership-transfers/scan`.
* `meeting_vote`: unique index `uq_meeting_vote_item_contract` (one counted vote per agenda item
  and unit); conflict records stay in `meeting_vote_conflict`. Insert races answer 409. The
  migration aborts on existing duplicates instead of deleting rows.
* `hoa_correction_report_setting.enabled` (default off) gates
  `GET /hoa/statements/{id}/correction-report` (409 when off); `GET/PUT
  /hoa/correction-report-settings` (tenant_settings permissions).
* Tests: `tests/integration/test_af08_hoa.py` (ownership scan, foreign reserve 422, levy
  difference after ownership change per AE10 variant), additions in `test_ae11_correction.py`
  and `test_ae31_online_vote_rule.py`.

## Filed statement PDFs (GAB-06, 11.3)

`statement_archive.archived_pdf` files the individual statement (per unit) and the total
statement once in the DMS (`documents.services.store_document`, source `generated`, links
`hoa_statement`, `property`, `legal_entity`, `unit` and the owner contacts of the year). The
transition to `issued` or `due` files every unit statement; the first CRM or portal output
files a missing one. Every later output returns the filed bytes (SHA-256 checked), so the
letter date and layout of an issued document never change. The filename carries version and
snapshot hash prefix: a new version files a new document. Gate G4 is checked before; no
statement value changes. Tests: `tests/integration/test_af11_statement_archive.py`.

## AG20 (wave 18): allocation proposal, GAE-11 and GAE-12 (migration 0438)

* `hoa/allocation_proposal.py`: switch `hoa_allocation_proposal_setting.enabled` (default off,
  `GET/PUT /hoa/allocation-proposal-settings`, `tenant_settings:*`). When on, the plan takeover
  preview adds `allocation_proposal` (`proposed`, `differs`) per row from `calc.allocation_owner`
  and `GET /hoa/statements/{id}/allocation-proposal` lists used owner (resolution date, M24-01)
  and proposal per unit (409 while off or without snapshot and resolution). Display only.
* `tests/integration/test_ag20_allocation.py`: statement with bound and unbound reserve payment
  end to end, plan ratio proposal; takeover proposal per variant.
* AG07 / GAF-32 (`portal_circular.py`, migration 0425): circular resolution in the owner
  portal. `GET /portal/circular-resolutions` lists running procedures (meeting kind
  `circular_resolution`, invited or held) of own units; `POST /portal/circular-resolutions/{id}/vote`
  stores one vote per unit and item (channel circular) with `portal_user_id` and
  `wording_sha256`, only with `hoa_online_meeting_setting.portal_circular_resolution_enabled`
  (default off, 403 MHVP-HOA-0037) and G4. CRM: `GET/PUT /hoa/portal-circular-settings`,
  `GET /hoa/portal-circular-votes?legal_entity_id=`, `GET /hoa/meetings/{id}/portal-circular-votes`
  (read only). Majority check unchanged. Test `tests/integration/test_ag07_portal_circular.py`.

## Welle 19 (AH05): Rücklagenzahlung über Bank, Mehrheitsprüfung bei Korrekturversion

- GAG-08 (GAE-11): `tests/integration/test_ah05_reserve_bank_majority.py` prüft die Jahresabrechnung Ende zu Ende mit CAMT.053-Import, Bankbuchung gegen die offenen Posten und zweckgebundener Rücklagenzahlung (`contributions_paid_by_reserve`, Saldo 001210, Restforderung, kein Doppelbuchen).
- GAG-15 (GAF-16): `POST /hoa/statements/{id}/new-version` mit `resolution_id` führt die Mehrheitsprüfung (M25-01) für den Korrekturbeschluss aus und liefert sie als `correction_majority_check` zurück. Nur Anzeige und Protokollvermerk, keine Statusänderung, keine Sperre. `GET /hoa/resolutions/{id}/majority-check` lehnt unbekannte Query-Parameter mit 422 ab.
- GAH-403: `new-version` lehnt einen Korrekturbeschluss einer anderen GdWE (legal_entity_id des Beschlusses ungleich legal_entity_id des Buchungskreises) mit 422 `MHVP-HOA-0038` ab; nichts wird angelegt. GAH-402: CRM-Dialog `StatementNewVersionDialog` (Grund, Grundlage, Korrekturbeschluss) mit Anzeige der Mehrheitsprüfung per `MajorityCheckLine`.
- GAG-22 (GAE-12): Planübernahme an `calc.allocation_owner` ist über `allocation_proposal.proposal_for` in `_plan_apply_preview` angebunden (Schalter, Standard aus); verifiziert mit `test_ag20_allocation.py`.

## Rundung (Welle 21, AJ01)

Alle `quantize` Aufrufe runden ausdrücklich ROUND_HALF_UP. `billing.calc.distribute` verteilt negative Summen vorzeichensymmetrisch und summentreu. Details und Schalter (`negative_costs_mode`, `remainder_mode`): docs/rules/RUNDUNG.md.

## Ereignisse der Finanzierung (AJ04, Welle 21)

Maßnahmen, Darlehen, Versicherungsfälle und ihre Positionen erzeugen Domainereignisse `hoa.measure.*`, `hoa.loan.*`, `hoa.insurance_claim.*` mit alt und neu (GAI-105).

## Folgen eines Beschlussstatus und Sonderumlage mit Ertragskonto (AN19, Welle 24)

- GAK-204: `PATCH /hoa/resolutions/{id}` mit Status `contested`, `annulled` oder `void` benachrichtigt die Nutzer mit `accounting:approve` (Art `hoa.resolution_contested`), sofern abhängige Wirtschaftspläne, Sonderumlagen oder Abrechnungen bestehen; nichts wird storniert (D54). `GET /hoa/resolutions/{id}/dependents` listet diese mit Kennzeichen `contested`. `POST /hoa/resolutions/{id}/review-deadline` legt eine Frist der Fristart `beschlussanfechtung` an (ohne Dauer: Datum Pflicht; mit vom Betreiber hinterlegter Dauer berechnet, zu verifizieren). Frage AN19-01, G4.
- GAK-205: Sonderumlage mit `revenue_account_id` (Ertragskonto der GdWE) und `reference_date` (nicht nach der ersten Fälligkeit), gespeichert in `snapshot.terms` und damit im beschlossenen Hash. Die Berechnung zeigt je Einheit den Eigentümer zum Stichtag und zur Fälligkeit (`owner_changed`); die Sollstellung folgt unverändert dem Eigentümer zur ersten Fälligkeit (AN19-03). Buchungsvorschlag nur als Entwurf hinter G4.
- AO04 (Welle 25, Migration 0457): `revenue_account_id` (FK `ledger_account`) und `reference_date` sind eigene Spalten von `special_levy` mit CHECK `reference_date <= first_due` (`ck_special_levy_reference_date_order`). Die Migration übernimmt die Werte aus `snapshot.terms` (unbekanntes Konto oder Stichtag nach der Fälligkeit bleibt NULL und wird protokolliert). Lesen und Schreiben über die Spalten; `snapshot.terms` wird bei der Berechnung aus den Spalten gespiegelt und bleibt Teil des Beschluss-Hashes. Sollstellung zum Stichtag weiterhin nicht umgesetzt (AN19-03 offen).
