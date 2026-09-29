# Wirtschaftsplan (7.8, W02)

| Field | Content |
| --- | --- |
| ID | W02 |
| Title | Wirtschaftsplan |
| Scope | WEG economic plan (M24): plan, resolution, takeover of the resolved advances into the payment plans of the ownership contracts |
| Source status | R04 (annex C, § 28 WEG: Wirtschaftsplan, Vorschüsse, Fälligkeit); court practice on details stays P01/P02 |
| Acceptance case | `tests/integration/test_m24_hoa.py` (plan, snapshot, resolution binding); `tests/integration/test_m12_letters_plan_export.py::test_plan_apply_preview_confirmation_second_person_idempotent` (takeover: 6.000,00 EUR by MEA 600/400 -> monthly 300,00 / 200,00; reserve 1.200,00 -> 60,00 / 40,00) |
| Implementation | `mhvp.hoa.calc.plan_results` (Gesamt- und Einzelplan, monthly amounts rounded per unit, difference shown), `mhvp.hoa.routers.transition_plan` (resolution bound to the snapshot hash, W06), `GET /hoa/plans/{id}/apply/preview` and `POST /hoa/plans/{id}/apply` (`mhvp.hoa.routers._plan_apply_preview`, `apply_plan`) |
| Change reason | M24, 23.09.2026; takeover into the payment plans as preview with confirmation and second person, M12 gaps 29.09.2026 |

## Rule

1. The draft of a plan changes nothing. A plan is taken over only in status `resolved`,
   `issued` or `due`, that is after a positive resolution bound to the calculated snapshot.
2. Takeover means: per unit of the snapshot and per component (`hoa_fee`, `reserve`) a
   standing monthly amount (`contract_payment`, reason `adjustment_from_statement`) on the
   ownership contract that owns the unit on `valid_from`, from `valid_from` on; the previous
   standing amount of the same type is closed on the day before (`mhvp.contracts.services.add_payment`).
   A unit without an ownership contract on `valid_from` is listed and skipped; a zero amount
   creates no row; a row with the same amount already starting on `valid_from` is unchanged.
3. The preview lists every row with the current and the new amount and the action. The
   takeover needs the confirmation of the preview (`confirm`) with the plan's current
   `snapshot_hash` and a person other than the plan's creator (`GATE_FOUR_EYES`). It is
   idempotent: `applied_at` marks a plan as taken over, a repeated call creates nothing.
4. No double charge of months already posted (R04): the preview counts receivable items
   already posted for months from `valid_from` on; the takeover never creates or changes
   receivables. An adjustment of posted months is a bookkeeping correction (reversal and new
   posting, rule 0.1.7) behind G1.

## What is and is not gated

| Step | Gate |
| --- | --- |
| Plan, items, calculation, internal approval, resolution | none (master data and resolution record; second person for the internal approval) |
| Preview of the takeover | none (`accounting:read`) |
| Takeover into the payment plans (rows on the ownership contracts) | none beyond `accounting:approve`, confirmation and second person: the rows are contract master data like the amounts entered in the contract UI (`docs/OPEN_QUESTIONS.md` VTR-01) |
| Monthly receivables from the rows (Sollstellungslauf) | G1 (productive bookkeeping) |
| Statement, issue, due, posting of the result | G4 |
