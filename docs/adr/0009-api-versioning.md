# ADR 0009: API versioning, deprecation headers and OpenAPI drift check

- Status: Accepted
- Date: 2026-09-26

## Context

Section 12 of `docs/MASTER-PROMPT.md` fixes the change rules of the public API: additive
changes without a version change, removals only with `v2`, deprecation headers at least six
months in advance. The TypeScript client (`packages/api-client`) and the integrations of
section 13 (smart-einzug, lexoffice, Immoware Hub replacement) are generated from
`apps/api/openapi.json`, so a removed path or field silently breaks them. Until now the rule
existed only as prose; `mhvp.core.versioning` (middleware and deprecation registry) was in
place without a decision record, without tests and without a check that stops a breaking
removal (backlog A50 in `docs/plans/LUECKENLISTE-2026-09-26.md`).

## Decision

1. **One major version in the path.** The base path stays `/api/v1` until a `v2` exists. A
   new major version is a new router prefix that runs in parallel to `v1`; `v1` is never
   changed incompatibly. The running application version (`Settings.app_version`, semantic
   version from `VERSION`) is announced on every HTTP response in the `API-Version` header
   (`mhvp.core.versioning.ApiVersionMiddleware`); it is informational and never negotiated.
2. **Additive changes need no version change.** New paths, new optional request fields,
   new response fields, new enum values on output and new event types are compatible and
   ship under `v1`. Clients must ignore unknown response fields.
3. **Breaking changes are removals and tightenings.** Removing a path, a method, a response
   field or a component property, making an optional request field required, narrowing a
   type or changing the meaning of a field is breaking and is only allowed
   - under a new major version (`/api/v2/...`) for paths and methods, and
   - after the affected `v1` element carried a deprecation mark for at least
     `MIN_NOTICE_MONTHS` (6) months.
4. **Deprecation is explicit and machine readable.** An endpoint is marked with the
   decorator `@deprecated(deprecated_on=..., sunset_on=..., successor=...)` (or
   `register_deprecation` for routes without access to the function). The mark
   - validates `sunset_on >= deprecated_on + 6 months` at import time,
   - adds the response headers `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) as IMF
     fixdates and, when a successor exists, `Link: <...>; rel="successor-version"`,
   - writes `deprecated: true`, `x-deprecated-on`, `x-sunset` and `x-successor` into the
     OpenAPI operation (`mark_deprecated_routes`, called in `create_app` after all
     routers).
   A field is deprecated with `Field(deprecated=True)` in its Pydantic schema, which
   renders `deprecated: true` on the property in the OpenAPI document. The change log
   entry names the replacement.
5. **The drift check enforces the rule.** `mhvp.openapi.breaking_removals(old, new, today)`
   compares the committed `apps/api/openapi.json` with the generated document and reports
   - a path or method that disappeared without `deprecated: true` and an `x-sunset` date
     on or before `today`,
   - a property of a component schema that disappeared without `deprecated: true` on the
     property in the committed document.
   `tests/unit/test_openapi.py` runs this comparison (fails the suite) and
   `python -m mhvp.openapi --check` (target `make openapi-check`, run by `make openapi`
   before the export) stops the regeneration of the committed file. A renamed component
   schema is not detected on property level; whole schema removals are reported only when
   the schema is still referenced.
6. **Sunset is not deletion.** After the sunset date the endpoint may be removed in `v1`
   only if a `v2` successor exists (rule 3); a `v1` endpoint without successor stays until the
   `v1` base path itself is sunset. Operator approval is required for every removal of a
   path that integrations use (section 13); removals of internal paths follow the same
   headers but need no approval.

## Consequences

- Tests: `apps/api/tests/unit/test_api_versioning.py` (month arithmetic, mark validation
  with the six months rule, headers on every response and on deprecated routes, registry
  fallback, OpenAPI marks) and `apps/api/tests/unit/test_openapi.py` (drift: removal without
  deprecation fails, removal after sunset passes, additive changes pass, committed document
  contains no undeclared removals).
- `make openapi` runs the drift check first; a breaking export must be preceded by the
  deprecation mark in a separate release, so the committed document always carries the mark
  before the removal.
- No `v2` exists today; nothing is deprecated. The first deprecation must also add the
  handbook note for API consumers (`docs/handbuch/`) and an entry in `CHANGELOG.md`.
- Open: version negotiation per request (`Accept-Version`) is not offered; the rate limit
  and idempotency middlewares of ADR 0008 run outside the version middleware and are not
  versioned.

## Alternatives considered

- Header based versioning (`Accept: application/vnd.mhvp.v2+json`): invisible in generated
  clients and in browser tools, harder to route through Traefik. Rejected; the master prompt
  fixes the path prefix.
- Date based versions per request (Stripe style): high maintenance for a platform with two
  tenants and a generated client. Rejected.
- Checking drift only by full equality with the committed file (the existing
  `test_committed_spec_is_current`): it stops silent changes but cannot tell an allowed
  additive change from a removal, so the developer would regenerate the file and lose the
  check. Kept as the first step; the removal check comes on top.

## References

- `docs/MASTER-PROMPT.md` section 12 (Änderungsregeln, Webhooks), section 13
- ADR 0008 (idempotency and rate limiting middlewares, middleware order)
- RFC 9745 (Deprecation header), RFC 8594 (Sunset header), RFC 8288 (Link relations)
- `apps/api/src/mhvp/core/versioning.py`, `apps/api/src/mhvp/openapi.py`
