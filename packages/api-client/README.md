# @mhvp/api-client

Typed TypeScript client for the mhvp API, generated with openapi-typescript and used through
openapi-fetch (section 4.2).

## Commands

| Command | Does |
| --- | --- |
| `pnpm api-client:generate` (or `make openapi`) | regenerate `src/schema.d.ts` from `apps/api/openapi.json` |
| `pnpm --filter @mhvp/api-client lint` / `typecheck` / `test` | ESLint, `tsc --noEmit`, Vitest |

## Contract

- `src/schema.d.ts` is generated; never edit it by hand.
- Source of truth is the committed `apps/api/openapi.json`. CI fails if the generated file
  drifts from the spec (build breaks on schema change without regeneration, section 4.2).
