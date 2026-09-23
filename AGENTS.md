<!-- GENERATED from docs/AGENT_RULES.md by scripts/sync_agent_docs.py, do not edit -->

# AGENTS.md

Instructions for Codex and other coding agents in this repository. The authoritative
specification is `docs/MASTER-PROMPT.md`; the shared rules below are identical to
`CLAUDE.md`.

Single source for `CLAUDE.md` and `AGENTS.md` (rule 0.1.11: no contradicting parallel rule
sets). Edit this file only, then run `make agent-docs` (or `python3 scripts/sync_agent_docs.py`).

## 1. Project identity

- Product: **MH Verwaltungsplattform**, codename `mhvp`. Product owner: Müller Holding AG.
  First tenant: Hausverwaltung Müller GmbH; second tenant: Timo Müller (Einzelunternehmen).
- Self hosted, multi tenant property management platform (WEG, rental, SEV) replacing
  Immoware24, API first, with three portals (section 1.2).
- Operator: Timo Müller.

## 2. Authoritative specification

`docs/MASTER-PROMPT.md` (version 2.0 Final) is binding. Reading path: section 0 (rules),
1 to 5 (goal, architecture, stack, tenants), 6 including 6.9 (data model), 7 (accounting and
statements), 8 to 15 (modules), 18 (plan with release gates), annex D (acceptance cases),
annex E (decided conflicts). Annex C is the source register for all legal rules. Read
sections selectively (rule 15); do not paraphrase the spec loosely, cite section numbers.

## 3. Session start checklist

1. Read `docs/OPEN_QUESTIONS.md` and `docs/ASSUMPTIONS.md`.
2. Check the status of the V and P items (19.1, C.2) and M1-xx items relevant to the task.
3. Read the current milestone plan in `docs/plans/`.
4. Confirm release gates G1 to G5 stay closed; nothing in the task may open them.

## 4. Working rules (section 0.1, condensed)

1. Development is released, money is not: productive bookkeeping, real payments, legally
   relevant statements and third party tenants stay locked until G1 to G5 (per tenant flags,
   default off). Set up the repo per section 17 and work the milestones of section 18 in
   order. Read existing code first and document deviations before changing it.
2. Keep the phase order of section 18. The early WEG check is no mandate to pull phase 4
   forward. The 6.9 schema decisions belong to the phase 1 schema so that the phase 4 WEG
   logic does not fail on an unsuitable core model; no other fields "auf Vorrat".
3. Uncertainty is no legal basis: never invent legal rules, interest, allocations, tax
   treatment or bank formats. Missing facts go to `docs/OPEN_QUESTIONS.md`; uncritical
   assumptions, labelled, to `docs/ASSUMPTIONS.md`. Risks to money, receivables, data
   protection, legal deadlines or evidence lock the affected productive action. A
   configurable value or disclaimer does not replace a valid rule.
4. API first: every function is offered via the documented API. Gate and lock rules also
   apply to jobs, imports, bulk actions and integrations.
5. Tenant and legal entity separation: the existing technical tenant separation stays
   unchanged; in addition receivables, balances, bank funds, reserves and deposits must be
   assigned to the correct legal entity (see section 8 below).
6. AI delivers proposals only; confidence is neither proof nor approval. No autonomous AI
   postings by default. Automatic postings remain a product goal, but only via explicitly
   activated, functionally released and deterministically verifiable rules (7.4). AI never
   alone approves new payees, IBAN changes, WEG resolutions, fees or tax classification.
7. Posted records stay traceable: drafts differ from postings; after posting, financial
   content is neither overwritten nor deleted; corrections only by reversal and, where
   needed, new posting. "Undo" of imports or AI never bypasses this or
   retention holds.
8. Independent expected results: domain tests use predefined, recomputable results. Annex D
   cases are requirements, not passed tests. Comparison with Immoware24 is an extra check.
9. Technical tests are mandatory: pytest with happy path, authorization, tenant separation,
   validation; for money flows also concurrency, retries, aborts, rollback, historical
   cut-off dates. Frontend component tests and Playwright for core paths. CI green.
   Tests not executed are reported explicitly as not executed.
10. Languages and numbers (section 9 below).
11. Documentation duties (section 10 below).
12. Per task: plan first, small traceable implementation, actually run tests, docs and result
    report. No unrequested large refactorings. Conventional Commits.
13. Security: no secrets in code; no production data export to AI without verified
    authorization and verified data processing. Existing technical security requirements
    remain. "EU endpoint", `AVV=true`, a role or a hash
    alone are no complete proof.
14. Done means: technical definition of done met, acceptance cases passed, required legal/tax
    decisions documented, relevant locks tested, original documents linked, no unresolved
    critical points for the released scope. A screen or a green test run alone is not enough.
15. Work economically: targeted search, no repeated full text dumps, no needless agent loops.
    Simple tasks go to low cost models or deterministic tools; demanding models are used for
    domain logic, architecture and error analysis. Economy never removes document checks, security checks or required tests.

## 5. Requirement types (section 0.2)

Rechtsgrundlage (norm from the source register, within its scope), Fachliche Umsetzung
(required function derived from the process), Produktschutz (stricter internal standard, never
claimed as legal duty), Offene Entscheidung (name owner and affected gate, never mark as
done by an assumption).

Neither the master prompt nor a review by two AI systems is a legal certification or an audit
of the actual software operation. The expert legal, tax and security review required before
productive use is a project release standard, not a claim that every WEG must have its annual
statement certified by an auditor (end of 0.2).

## 6. Precedence (section 0.3)

Short statements from version 1.1.1 apply only as specified in 0.3. Conflicts E01 to E16 are
decided in section 6.9 and annex E; follow them. A new conflict: do not weaken the functional
requirement; write an ADR with conflict, impact and minimal proposal, present it to the
operator, keep the function behind a feature flag until decided.

## 7. Release gates

G0 start (done), G1 productive bookkeeping, G2 payment initiation, G3 rental statements, G4
WEG statements, G5 third party tenants (section 18.0). Per tenant, default closed, no global
override (ADR 0003). A gate covers only the documented scope. Gates never replace domain
checks.

## 8. Tenant and legal entity separation

- RLS on every tenant table via `mhvp.core.db.rls.tenant_rls_statements()`; runtime role is
  never superuser, BYPASSRLS or owner (section 5.3, ADR 0002).
- Legal entity separation is a separate axis: ledger per `legal_entity` (6.9.1, E01).
  Receivables, balances, bank funds, reserves and deposits belong to the right legal entity;
  a management company is not automatically creditor or owner of managed funds.
- Money and booking invariants B01 to B09: section 7.1. Rule index: `docs/rules/README.md`.

## 9. Languages and formats (rule 10)

- English: code, identifiers, commits, comments, technical documentation.
- German: UI, domain terms, handbook, operator documents (`docs/OPEN_QUESTIONS.md`,
  `docs/ASSUMPTIONS.md`, `docs/acceptance/`, `docs/handbuch/`, `docs/integrations/`).
  German texts use no dashes as sentence punctuation.
- UI formats `TT.MM.JJJJ` and `1.234,56 EUR`; internally ISO 8601. No float for money:
  `NUMERIC(14,2)` for amounts, `NUMERIC(20,8)` for intermediate values and ratios (6.9.8).
- Timestamps `TIMESTAMPTZ` in UTC; IDs UUID v7 (section 4.1).

## 10. Documentation duties (rule 11)

- README per module; architecture decisions as ADR in `docs/adr/` (template `0000-template.md`).
- New or changed domain rules are registered in `docs/rules/` with: ID, scope, source status
  (annex C), acceptance case (annex D), change reason.
- Errors per ADR 0004 with codes registered in `mhvp.core.problems`.

## 11. Per task workflow

Rule 0.1.12 and section 17:

1. Read the issue or task; plan in `docs/plans/<milestone>.md` with files, migrations, tests.
2. Feature branch; implement in small commits (Conventional Commits).
3. Run tests; report tests not executed explicitly. Check the OpenAPI diff.
4. Update docs (README, module README, ADR, OPEN_QUESTIONS, ASSUMPTIONS).
5. Pull request with summary and open points; CI green; merge.
6. Deploy to staging; acceptance by the operator against the acceptance criteria.
7. Result report: what was done, test results, open points.

## 12. Commands (Makefile)

| Target | Does |
| --- | --- |
| `make dev` | start the dev stack (Docker Compose, `.env`) |
| `make down` | stop the dev stack |
| `make migrate` | `alembic upgrade head` in the migrate container (or locally with `LOCAL=1`) |
| `make test` | `make test-api` and `make test-web` |
| `make test-api` | `cd apps/api && uv run pytest` |
| `make test-web` | web and package tests via pnpm |
| `make e2e` | Playwright smoke tests of both web apps |
| `make lint` | ruff, eslint, agent docs sync check |
| `make typecheck` | mypy strict and `tsc --noEmit` |
| `make openapi` | export `apps/api/openapi.json` and regenerate `packages/api-client` |
| `make db-bootstrap` | run `infra/postgres/bootstrap.sh` against `PGHOST` |
| `make agent-docs` | regenerate `CLAUDE.md` and `AGENTS.md` from this file |
| `make seed`, `make ai-eval`, `make deploy`, `make backup-verify` | not yet available (M2/M7/M9), exit 2 |

## 13. Repository map

| Path | Content |
| --- | --- |
| `apps/api/` | FastAPI, Alembic, Celery (Python package `mhvp`, domains under `src/mhvp/`) |
| `apps/web-crm/`, `apps/web-portal/` | Next.js 15 apps |
| `packages/api-client/`, `packages/ui/`, `packages/config/` | generated client, shared UI, shared config |
| `infra/` | Compose files, Traefik (dev), PostgreSQL bootstrap, object storage |
| `scripts/` | helper scripts, `sync_agent_docs.py` |
| `docs/` | spec, plans, ADRs, rules, acceptance cases, runbooks, handbook, integrations |

## 14. Escalation

Anything touching money, receivables, data protection, legal deadlines or evidence without a
released rule stays locked and goes to `docs/OPEN_QUESTIONS.md` with owner and affected gate.
Work continues on other tasks.
