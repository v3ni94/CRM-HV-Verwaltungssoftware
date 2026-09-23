# ADR 0004: Error format

- Status: Accepted
- Date: 2026-09-23

## Context

Section 4.1 requires RFC 9457 problem details (`application/problem+json`) with error codes
`MHVP-<Domäne>-<Nummer>`, a German user text and an English developer text.

## Decision

Every error response has content type `application/problem+json` and the fields:

| Field | Content |
| --- | --- |
| `type` | `urn:mhvp:problem:<code>` |
| `title` | German user text |
| `status` | HTTP status |
| `detail` | German detail |
| `instance` | request path |
| `code` | `MHVP-<DOMAIN>-<NNNN>` |
| `developer_message` | English text for developers |
| `correlation_id` | request correlation id |
| `errors` | optional list of field errors: `location`, `code`, German `message` |

Codes are registered centrally in `mhvp.core.problems`; unregistered codes are not allowed.
Every response carries `X-Correlation-ID`; a valid UUID from the request is accepted,
otherwise a new one is generated. No hosts, credentials or stack traces in any field.

## Consequences

- Clients can rely on stable machine readable codes; UIs show `title`/`detail` directly.
- Tests cover 404, 405, 422, 500 and closed gate (`MHVP-GATE-0001`).

## Alternatives considered

- FastAPI default `{"detail": ...}`: not RFC 9457, no codes.
- `about:blank` types or HTTP URLs: a URN avoids promising a resolvable documentation URL.

## References

- `docs/MASTER-PROMPT.md` section 4.1
- `docs/plans/M1.md` section 4.3
