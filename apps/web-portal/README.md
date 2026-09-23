# @mhvp/web-portal

Next.js 15 (App Router) app of the MH Verwaltungsplattform: portals for tenants, owners and service providers (production hosts `portal.muellerhv.de`, `portal.mueller-holding.ag`). Milestone M1 delivers only
the skeleton; domain functions follow from M2 (see `docs/plans/`).

## Commands

| Command | Does |
| --- | --- |
| `pnpm --filter @mhvp/web-portal dev` | dev server on port 3001 |
| `pnpm --filter @mhvp/web-portal build` / `start` | production build and server (port 3001) |
| `pnpm --filter @mhvp/web-portal lint` | ESLint, no warnings allowed |
| `pnpm --filter @mhvp/web-portal typecheck` | `tsc --noEmit` |
| `pnpm --filter @mhvp/web-portal test` | Vitest component and route tests |
| `pnpm --filter @mhvp/web-portal e2e` | Playwright smoke tests |

In the Compose dev stack the app is served at `http://portal.localhost`.

## Contract (`docs/plans/M1.md` section 4.5)

- `GET /api/health` returns `{"status": "ok", "service": "web-portal", "version": "<semver>"}`.
- The German home page shows the product name and a server rendered API status line using
  `@mhvp/api-client` against `MHVP_API_INTERNAL_URL` + `/api/v1/health/ready`.
- i18n with next-intl, default `de-DE`. No invented CI colours or logos: neutral tokens from
  `@mhvp/ui` until the CI values are released (V14, OPEN_QUESTIONS M1-08).
- All data access goes through the documented API (rule 0.1.4).
