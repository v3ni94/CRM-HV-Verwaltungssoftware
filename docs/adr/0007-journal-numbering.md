# ADR 0007: Journal numbering

Status: accepted (Coding-Agent decision per MASTER-PROMPT 7.1 B04), 23.09.2026.

## Context

B04 requires a continuous register per number range without reuse or silent renumbering and
leaves the choice of a strictly gapless procedure to the implementation. A database sequence
does not guarantee gaplessness (rollbacks consume values).

## Decision

Numbers are assigned per ledger and fiscal year at posting time from a counter row
(`journal_number_counter`) locked with `SELECT ... FOR UPDATE` inside the posting
transaction. A rolled back posting releases the number together with the counter update, so
no gap arises. Drafts carry no number. The fiscal year is labelled by its starting calendar
year (`ledger.fiscal_year_start_month`).

## Consequences

Posting in the same ledger and year is serialised; postings in different ledgers run in
parallel. The concurrency test posts ten drafts in parallel sessions and expects 1 to 10.
No claim is made that every gap would violate GoBD.
