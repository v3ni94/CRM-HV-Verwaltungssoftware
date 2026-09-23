# @mhvp/ui

Shared React components and design tokens for `web-crm` and `web-portal` (section 17).

## Commands

| Command | Does |
| --- | --- |
| `pnpm --filter @mhvp/ui lint` / `typecheck` / `test` | ESLint, `tsc --noEmit`, Vitest |

## Contract

- `src/tokens.css` holds neutral design tokens only. Tenant colours and logos come later from
  the API (`/api/v1/tenant/branding`, M2); no CI values are invented (V14, OPEN_QUESTIONS M1-08).
- Components are exported from `src/index.ts` and have component tests.
