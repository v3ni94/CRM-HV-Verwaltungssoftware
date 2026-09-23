# @mhvp/web-crm

Next.js 15 (App Router) app of the MH Verwaltungsplattform: administration interface (Verwaltung, production host `crm.mueller-holding.ag`). Milestone M1 delivers only
the skeleton; domain functions follow from M2 (see `docs/plans/`).

## Commands

| Command | Does |
| --- | --- |
| `pnpm --filter @mhvp/web-crm dev` | dev server on port 3000 |
| `pnpm --filter @mhvp/web-crm build` / `start` | production build and server (port 3000) |
| `pnpm --filter @mhvp/web-crm lint` | ESLint, no warnings allowed |
| `pnpm --filter @mhvp/web-crm typecheck` | `tsc --noEmit` |
| `pnpm --filter @mhvp/web-crm test` | Vitest component and route tests |
| `pnpm --filter @mhvp/web-crm e2e` | Playwright smoke tests |

In the Compose dev stack the app is served at `http://crm.localhost`.

## Contract (`docs/plans/M1.md` section 4.5)

- `GET /api/health` returns `{"status": "ok", "service": "web-crm", "version": "<semver>"}`.
- The German home page shows the product name and a server rendered API status line using
  `@mhvp/api-client` against `MHVP_API_INTERNAL_URL` + `/api/v1/health/ready`.
- i18n with next-intl, default `de-DE`. No invented CI colours or logos: neutral tokens from
  `@mhvp/ui` until the CI values are released (V14, OPEN_QUESTIONS M1-08).
- All data access goes through the documented API (rule 0.1.4).
