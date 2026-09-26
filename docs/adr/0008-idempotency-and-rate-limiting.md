# ADR 0008: Idempotency-Key middleware and rate limiting

- Status: Accepted
- Date: 2026-09-26

## Context

Section 12 of `docs/MASTER-PROMPT.md` requires an `Idempotency-Key` header for all writing
endpoints (repetitions return the same answer) and rate limits per token with
`X-RateLimit-*` headers. Until now only journal entries (advisory lock plus
`JournalEntry.idempotency_key`), levies and HOA statements carried their own idempotency, and
no rate limit existed in the API (backlog A48, A49 in `docs/plans/LUECKENLISTE-2026-09-26.md`).
Both concerns cut across every router, so they belong to `mhvp.core` as pure ASGI
middlewares rather than to each endpoint.

## Decision

1. **Storage in Redis, no table.** The application already holds a Redis client in
   `app.state.resources` (readiness check, Google Calendar cache). Idempotency records and
   rate counters live there with a TTL; no migration, no cleanup job. A Redis restart loses
   at most 24 hours of idempotency records and the current minute of counters, which is
   acceptable because both are protective, not financial, records: postings keep their own
   database side idempotency (7.1, ADR 0007).
2. **Idempotency (`mhvp.core.idempotency.IdempotencyMiddleware`).** Active only for POST,
   PUT, PATCH and DELETE requests that carry `Idempotency-Key` and an identity (verified
   bearer token or parsed API key). Scope is tenant plus actor (`user:<id>` or
   `apikey:<prefix>`); the same key in another tenant or from another user is a different
   record. The first call takes the record with `SET NX EX 86400` in state `in_progress`
   together with a SHA-256 fingerprint of method, path and body. Outcomes:
   - same key, different fingerprint: 422 `MHVP-CORE-0007`;
   - same key while the first call runs: 409 `MHVP-CORE-0008` with `Retry-After: 1`;
   - same key after completion: stored status, `Content-Type` and body are replayed with
     `Idempotent-Replayed: true`;
   - empty or overlong key (more than 255 characters): 422 `MHVP-CORE-0009`.
   Answers with status 5xx, exceptions and bodies above 1 MB release the record so that a
   retry executes again. 4xx answers are stored: they are deterministic for the same input.
   Endpoints with their own idempotency stay unchanged; without the header the middleware is
   inert, so existing clients and tests keep working.
3. **Rate limiting (`mhvp.core.ratelimit.RateLimitMiddleware`).** Fixed window of one
   minute with `INCR` and `EXPIRE` per subject: authenticated requests per tenant and actor
   (`Settings.rate_limit_per_minute_user`, default 600), unauthenticated requests per client
   address (`Settings.rate_limit_per_minute_anonymous`, default 120; covers login, MFA and
   inbound webhooks). Every answer carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
   `X-RateLimit-Reset` (seconds until the window ends). Exceeding the limit yields 429
   `MHVP-CORE-0006` with `Retry-After`. `/api/v1/health/*` is exempt. The limits are
   operator configuration (Produktschutz), not a legal rule.
4. **Fail open on Redis errors.** If Redis is unavailable the rate limiter lets the request
   pass without headers and logs `ratelimit_unavailable`; Traefik keeps the edge limit
   (section 3). The idempotency middleware is only reached with the header and does not
   swallow Redis errors on the first `SET`: a client that explicitly asks for idempotency gets
   a 500 problem instead of a silently non idempotent execution.
5. **Middleware order** (outer to inner): correlation id, rate limit, idempotency, routers.
   Replays count against the rate limit like any other request.
6. `X-Forwarded-For` is only honoured with `Settings.rate_limit_trust_forwarded_for=true`
   (behind Traefik); otherwise the socket address is used, so the header cannot be spoofed
   in a direct deployment.

## Consequences

- New settings `MHVP_RATE_LIMIT_ENABLED`, `MHVP_RATE_LIMIT_PER_MINUTE_USER`,
  `MHVP_RATE_LIMIT_PER_MINUTE_ANONYMOUS`, `MHVP_RATE_LIMIT_TRUST_FORWARDED_FOR`.
- New problem codes `MHVP-CORE-0006` to `MHVP-CORE-0009` in `mhvp.core.problems`.
- Identity for middlewares (`mhvp.core.request_identity`) verifies the token signature but
  does not check API key secrets or memberships against the database; a forged key gains
  only its own namespace and is rejected by the endpoint.
- Tests: `apps/api/tests/integration/test_m2_idempotency_ratelimit.py` (replay without
  second effect, differing body 422, running first call 409, tenant and user separation,
  stored 4xx replay, headers and health exemption, 429 with a low limit via settings
  override).
- Open: sliding window and per endpoint budgets (for example cheaper limits for bulk
  imports) are not implemented; the stored response keeps only `Content-Type`, no other
  headers such as `Location`; multi worker deployments share the same Redis, so the limit is
  global per subject.

## Alternatives considered

- Table `idempotency_key` with a Celery cleanup job: more moving parts, needs RLS and a
  migration, and adds a database round trip to every idempotent write. Rejected while Redis
  is already a mandatory runtime dependency.
- Sliding window log (sorted sets): more exact at window boundaries but more Redis traffic
  per request; a fixed window suffices for a protective limit and is easy to reason about.
- Per endpoint decorator instead of middleware: would leave gaps (rule 0.1.4 applies gate and
  lock rules to every write path) and duplicate code across routers.

## References

- `docs/MASTER-PROMPT.md` section 12 (Idempotenz, Rate-Limits), section 3 (Traefik), 7.1
- ADR 0004 (error format), ADR 0007 (journal numbering and entry idempotency)
- `docs/plans/LUECKENLISTE-2026-09-26.md` A48, A49
