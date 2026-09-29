# ADR 0014: Learning bookkeeper (staged automation, decision log, learned rules)

- Status: Proposed (steps S0 and S1 implemented; operator decisions M12-05 to M12-08 open)
- Date: 2026-09-28

## Context

The operator's vision is a bookkeeping that remembers corrections, proposes postings from
its own history and, later, posts recurring unambiguous cases without a click. The master
prompt allows automation only through explicitly activated, functionally released and
deterministically verifiable rules (0.1.6, 6.9.4, 7.4 no. 4), forbids learning from anything
but confirmed results (7.4 no. 6), keeps posted records immutable (0.1.7, B03) and keeps
money behind the gates G1 and G2 (18.0, ADR 0003). The gap analysis of 28.09.2026
(`docs/plans/M12-lernender-buchhalter-und-luecken-2026-09-28.md`) found: stage 1 proposals
are computed on read and stored nowhere, the booking does not know which proposal it came
from, rejections are impossible in the bank UI, `AiProposal` rows stay pending forever,
`journal_entry.reversed` is free text only, bank rule lifecycle changes emit no events and
`rule_matches` exists twice. Without a persisted ground truth nothing can be learned or
measured (rule 0.1.8).

## Decision

1. Architecture as in plan section 3.1: everything lives in `mhvp.banking`; `mhvp.ai` is
   only called (rejections through `mhvp.ai.examples.record_rejection`), never extended by
   the banking side. Accounting never imports banking: a reversal reaches the bank side through
   the domain event `journal_entry.reversed` consumed by the watermark job
   `mhvp.banking.events_consumer` (pattern `automation.services.process_tenant`, own table
   `banking_event_watermark`, beat task `mhvp.banking.process_events` every minute).
2. Decision log `posting_decision` (S1): one row per bank transaction and decision round with
   the snapshot of all stage 1 proposals as shown, `engine_version`
   (`posting_proposal.ENGINE_VERSION`), `rule_version` and `features_hash`
   (`mhvp.banking.features`), case kind, level (always `L0` until S4), best source and
   confidence, then the decision of a person: `accepted_unchanged` (exactly the chosen
   proposal booked), `modified` (diff against the chosen proposal, `BookIn.proposal_id` and
   `chosen` make the choice of the second proposal a choice, not a modification), `rejected`
   (mandatory reason, transaction stays open, next round opened), `ignored` (reason,
   reopenable through `POST /banking/transactions/{id}/reopen`), `expired` (snapshot replaced
   because the facts changed) and `reversed` (counter example written by the consumer when
   the booked entry was reversed). `auto_posted` is reserved for the runner (S6).
   `BankTransaction.status` stays as it is; the unused status `proposed` is never set.
3. Append only in the sense of B03: the DB trigger `mhvp_posting_decision_guard` forbids
   `DELETE`, allows exactly one transition from `pending` to a closed state (decision columns
   filled, snapshot columns immutable) and refuses every update of a closed row. At most one
   pending row per transaction (partial unique index). Bulk confirmations are marked
   (`bulk = true`) and count with lower weight later.
4. Snapshots are computed by the Celery task `mhvp.banking.compute_proposals` after the
   commit of every import path (file import and CSV import through an after-commit hook,
   finAPI and FinTS inside their worker tasks after their own commit), idempotent per
   `BankSyncRun` and transaction (same `features_hash`: no new row; changed hash: old row
   `expired`, new round). Never inside the import request. A person deciding before the job
   ran gets a snapshot at decision time. The job and a manual booking serialise on the
   transaction row lock; the job skips a transaction that is no longer `new`.
5. Tenant switch `tenant_settings.learning_bookkeeper_enabled`, default off, changed only via
   `PUT /banking/learning` (accounting:approve plus tenant_settings:update, reason, event
   `tenant.learning_bookkeeper_changed`). With the switch off nothing is written and booking,
   ignoring and rejecting behave exactly as before. The switch posts nothing and opens no
   gate. Its productive activation is blocked by the data protection review of the store
   (OPEN_QUESTIONS M12-06): the rows carry pseudonymous payer data (IBAN fingerprint,
   identifiers), the stored feature summary contains no names, no full purpose and no plain
   IBAN.
6. Corrections: `services.reverse` takes a reason code (`ReversalReason`: input_error,
   wrong_assignment, wrong_amount, wrong_date, duplicate, bank_return, run_reversal,
   automation_error, other) stored on the reversal entry (`reversal_reason_code`) next to the
   mandatory free text; the event `journal_entry.reversed` carries it. The consumer turns a
   reversed bank posting into a `reversed` counter example row, sets the transaction back to
   `new` (the entry id stays as history) and `matching.book_payment` accepts a transaction
   whose effective entry is reversed for exactly one new posting (Storno plus Neubuchung).
7. Technical preparation (S0): index `ix_journal_entry_bank_transaction`, one
   `rule_matches` implementation (`posting_proposal.rule_matches` on dicts,
   `matching.rule_matches` adds the legal entity check and delegates), lifecycle events
   `bank_rule.proposed`, `bank_rule.approved`, `bank_rule.activated`, `bank_rule.disabled`
   (`superseded` and `downgraded` named for S5 and S6) and `invoice.updated`.
8. Levels, learned rules, verifiers, the runner, the review queue and the AI tie breaker
   follow in S3 to S10 of the plan and each get their own addendum here. Nothing in S0 and
   S1 posts automatically; the existing `POST /banking/auto-post` is unchanged.

## Consequences

- Every human decision in the bank reconciliation becomes recorded evidence with the shown
  alternatives, so precision per case kind and the streaks for rule proposals (S5) can be
  computed from data instead of guessed.
- Migration 0232 (down_revision 0231, rechained at integration on 29.09.2026): columns
  `journal_entry.reversal_reason_code`, `tenant_settings.learning_bookkeeper_enabled`, index
  `ix_journal_entry_bank_transaction`, tables `posting_decision` (RLS, guard trigger) and
  `banking_event_watermark` (RLS).
- Error code `MHVP-BANK-0021` (stale proposal id). New endpoints
  `POST /banking/transactions/{id}/reject`, `POST /banking/transactions/{id}/reopen`,
  `GET /banking/transactions/{id}/decisions`, `GET`/`PUT /banking/learning`; `BookIn` gains
  `discount`, `proposal_id`, `chosen`; `GET .../posting-proposals` gains `learning`.
- Tests: `tests/unit/test_posting_decision_diff.py`,
  `tests/integration/test_m12_posting_decisions.py` (switch, 403, tenant and legal entity
  separation, idempotency, refresh, stale id, rejection, ignore and reopen, reversal through
  the consumer with rebooking, DB guard, rule events, bulk marker, job against manual booking).
- Open operator decisions (OPEN_QUESTIONS): M12-05 outgoing automation, M12-06 data
  protection review of the decision store (hard precondition of the switch), M12-07
  comparison postings by automation before G1 (recommendation: offline replay only), M12-08
  sampling instead of daily review (L3).
- Retention of `posting_decision` (proposal 24 months, daily job after the pattern
  `ai_examples_retention`, evidence of active rules kept) is part of M12-06 and implemented
  with S5.

## Alternatives considered

- Recording decisions on `AiProposal`: rejected, the AI table belongs to another owner, has no
  place for deterministic proposals and would tie learning to a provider.
- Strict insert only with one row per state (no update at all): rejected, the plan requires
  at most one pending row per transaction, which needs the pending row to close; the guard
  trigger keeps the protected property (no rewrite of a closed decision, no delete).
- Computing snapshots in the import request: rejected (N+1 in the request, plan 3.1 no. 2).
- Confidence driven automatic posting: rejected by the specification (0.1.6, 7.4 no. 3 and 4).

## References

- `docs/MASTER-PROMPT.md` sections 0.1.6, 0.1.7, 0.1.8, 6.9.4, 7.1 (B01 to B09), 7.4, 9.2,
  15.1, 18.0; annex D cases D39, D51.
- `docs/plans/M12-lernender-buchhalter-und-luecken-2026-09-28.md` sections 3.1 to 3.6, 4.
- `docs/rules/M12-04-lernender-buchhalter.md`, `docs/rules/B03.md`, `docs/rules/M12-01-kontierung-zwei-stufen.md`.
- ADR 0002 (tenant isolation), ADR 0003 (release gates), ADR 0004 (error codes), ADR 0010
  (learning examples).
