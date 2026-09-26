# ADR 0011: Gate approval by superadmin without four eyes

- Status: Accepted as operator decision (26.09.2026), implemented behind a platform flag that is off
- Date: 2026-09-26

## Context

ADR 0003 (decision 5) and `docs/MASTER-PROMPT.md` section 18.0 make opening a release gate G1 to
G5 an auditable act with evidence that requires two distinct persons: one platform administrator
files the request in the tenant, another platform administrator approves it
(`MHVP-GATE-0002`, `mhvp.platform.routers._decide`). `docs/OPEN_QUESTIONS.md` M2-02 asked the
operator to name that second person.

Operator decision of 26.09.2026 (M2-02): besides the operator account there will be two further
platform administrators (names to follow). The operator account is to act as "Superadmin" and
must be able to approve release gates alone, without a second person.

This is a new conflict in the sense of section 0.3: the request would silently weaken the
functional requirement "request and approval by different persons". Section 0.3 asks for an
ADR with conflict, impact and a minimal proposal, presentation to the operator, and a feature
flag until the decision is taken. The gates guard money: G1 productive bookkeeping, G2 payment
initiation, G3 rental statements, G4 WEG statements, G5 third party tenants.

## Impact

- **Second control is lost for the money gates.** With the bypass a single account can both
  file and approve the opening of productive bookkeeping, real payments and legally relevant
  statements for a tenant. A compromised or mistaken superadmin session is enough to open every
  gate. ADR 0003 introduced the two person rule exactly against this.
- **Audit and evidence.** The opening record remains auditable, but it no longer proves that a
  second person checked the evidence. Anyone relying on the audit trail (tax adviser, auditor,
  WEG owners, courts) sees an approval that the requester gave himself. The record therefore
  carries `four_eyes = false` and the audit event marks the bypass so this weakness is never
  hidden.
- **Liability.** Whether a self approved release meets the operator's own due diligence and
  organisational duties towards owners, tenants and third party tenants (G5) is a legal
  question; this ADR does not answer it. Assessment by the operator's lawyer or tax adviser is
  recommended before the flag is switched on for a productive tenant (Produktschutz, rule 0.2).
- **Domain checks stay untouched.** The gate bypass does not touch four eyes rules inside the
  domain (payment release, IBAN approval, WEG resolutions, invoice approval, ADR 0003 decision 6).

## Decision

1. **Platform flag, default off.** New platform table `platform_settings` (single row, no
   tenant, no RLS, migration 0135) with `gate_superadmin_bypass = false`. Only a platform
   administrator can read or change it (`GET`/`PATCH /api/v1/platform/settings`). Every change
   is written to the application log with actor, old and new value and version. With the flag
   off the behaviour of ADR 0003 stays exactly as today: 403 `MHVP-GATE-0002` for a self
   approval, 409 `MHVP-GATE-0003` for a second decision.
2. **Exactly one superadmin.** `app_user.is_superadmin` (migration 0135) with a partial unique
   index, so at most one user holds the marker. The marker can only be granted to an active
   platform administrator (`PUT`/`DELETE /api/v1/platform/users/{id}/superadmin`,
   `GET /api/v1/platform/superadmin`, service `mhvp.platform.services.set_superadmin`). The seed
   grants it to the seed administrator when `MHVP_SEED_ADMIN_SUPERADMIN=true` is set
   (`MHVP_SEED_ADMIN_EMAIL` stays the only place where the operator address appears; the
   address is never part of application logic).
3. **Bypass scope.** Only an *approval* by the superadmin of his *own* request, only while the
   flag is on. Self rejection, any other platform administrator, API keys and tenant
   administrators keep the two person rule. The bypass never opens a gate in another tenant;
   the request is decided within the tenant transaction of its own tenant.
4. **Marked record and audit.** The approved request carries `four_eyes = false`
   (`release_gate_request.four_eyes`, exposed in `GateRequestOut`). The event
   `release_gate.opened` carries `four_eyes: false` and `superadmin_bypass: true` in its payload
   and the audit log the change `four_eyes: true -> false`; the application log records
   `release_gate_superadmin_bypass` with tenant, request, gate and actor.
5. **No further weakening.** No global environment switch, no tenant setting, no API key path,
   no bypass of `MHVP-GATE-0003`, no effect on revocation and no effect on domain four eyes
   rules. A second superadmin requires a new ADR.

## Consequences

- The operator can open gates alone once he switches the flag on; until then nothing changes
  and the two person rule of ADR 0003 stands. The default of the flag is off in code, migration
  and seed, and no script in the repository switches it on.
- Tests: `apps/api/tests/integration/test_m2_gate_superadmin.py` (flag off keeps 403 and 409
  also for the superadmin, flag on lets the superadmin approve alone with audit entry and marked
  record, a non superadmin cannot approve his own request even with the flag on, only one
  marker at a time, tenant separation of the approval), `test_m2_platform.py` unchanged.
- Documentation: rule `docs/rules/M2-02.md`, `docs/OPEN_QUESTIONS.md` M2-02, this ADR.
- Recommendation to the operator (not a legal statement): keep the flag off for productive
  tenants and use it, if at all, only for staging and for the operator's own tenants; enter
  the two further platform administrators first so that the regular path remains available.

## Alternatives considered

- Remove the four eyes rule for all platform administrators: rejected, it would weaken the
  control for everyone and contradicts ADR 0003 without any mark in the record.
- Let the superadmin approve after a waiting period or with a second factor: rejected as
  scope creep; a second TOTP entry by the same person is not a second person.
- Refuse the request: not possible under section 0.3, the operator decides; the flag keeps the
  requirement intact until he does.

## References

- `docs/MASTER-PROMPT.md` sections 0.1 (rules 1, 3, 4, 13), 0.2, 0.3, 18.0, 19.2
- ADR 0003 (release gates), ADR 0004 (error codes), ADR 0006 (identity)
- `docs/OPEN_QUESTIONS.md` M2-02; `docs/rules/M2-02.md`
- Migration `apps/api/alembic/versions/0135_gate_superadmin_bypass.py`
