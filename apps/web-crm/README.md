# @mhvp/web-crm

Next.js 15 (App Router) app of the MH Verwaltungsplattform: administration interface (Verwaltung, production host `crm.mueller-holding.ag`). M1 delivered the skeleton; M2 adds
login with TOTP and tenant switch, M3 the contact screens (CRUD, duplicate proposal, full text
search). See `docs/plans/`.

## Commands

| Command | Does |
| --- | --- |
| `pnpm --filter @mhvp/web-crm dev` | dev server on port 3000 |
| `pnpm --filter @mhvp/web-crm build` / `start` | production build and server (port 3000) |
| `pnpm --filter @mhvp/web-crm lint` | ESLint, no warnings allowed |
| `pnpm --filter @mhvp/web-crm typecheck` | `tsc --noEmit` |
| `pnpm --filter @mhvp/web-crm test` | Vitest component and route tests |
| `pnpm --filter @mhvp/web-crm e2e` | Playwright smoke tests (tests tagged `@backend` are skipped) |
| `scripts/e2e-backend.sh` (repo root) | Playwright including `@backend` tests against a real API (see below) |

In the Compose dev stack the app is served at `http://crm.localhost`.

## Contract (`docs/plans/M1.md` section 4.5)

- `GET /api/health` returns `{"status": "ok", "service": "web-crm", "version": "<semver>"}`.
- The German home page shows the product name and a server rendered API status line using
  `@mhvp/api-client` against `MHVP_API_INTERNAL_URL` + `/api/v1/health/ready`.
- i18n with next-intl, default `de-DE`. No invented CI colours or logos: neutral tokens from
  `@mhvp/ui` until the CI values are released (V14, OPEN_QUESTIONS M1-08).
- All data access goes through the documented API (rule 0.1.4).

## Authentication (backend for frontend)

The browser never sees API tokens. Route handlers under `src/app/api/session/*` call the API
server side (`MHVP_API_INTERNAL_URL`) and keep the tokens in cookies:

| Cookie | Content | Lifetime |
| --- | --- | --- |
| `mhvp_mfa` | MFA token of login step 1 | 10 minutes |
| `mhvp_at` | access token | `expires_in` minus 30 s |
| `mhvp_rt` | refresh token (rotating) | 30 days |
| `mhvp_ctx` | current tenant id and the tenant list of the last token response | 30 days |

All cookies are `httpOnly`, `SameSite=Strict`, `Path=/`, and `Secure` on every host except
`localhost`, `127.0.0.1` and `*.localhost`.

| Handler | API call |
| --- | --- |
| `POST /api/session/login` | `/auth/login`, sets `mhvp_mfa` |
| `POST /api/session/mfa/setup` | `/auth/mfa/setup`, returns secret and the otpauth URI as QR code (data URL rendered server side with `qrcode`) |
| `POST /api/session/mfa/verify` | `/auth/mfa/verify` (optional `tenant_id`), sets the session cookies |
| `POST /api/session/tenant` | `/auth/switch-tenant`, then revokes the previous session via `/auth/logout` |
| `POST /api/session/logout` | `/auth/logout`, clears all cookies |
| `GET /api/session/refresh?next=` | rotates the refresh token for server components (they cannot write cookies) |

- `src/middleware.ts` (Node.js runtime) redirects unauthenticated page requests to `/anmelden`
  (API paths get a 401 problem), renews an expired access token with the refresh token before
  rendering, and sends sessions without a tenant to `/mandant`. Public: `/`, `/anmelden*`,
  `/api/health`, `/api/session/*`.
- `src/lib/api-server.ts` wraps the generated `@mhvp/api-client` with the bearer from the cookie
  and refreshes once on 401. Concurrent refreshes with the same token share one API call
  (rotation plus reuse detection would otherwise revoke the session family).
- CSRF: `SameSite=Strict` plus a same-origin `Origin` check (`src/lib/csrf.ts`) in every mutating
  handler.
- `src/app/api/bff/[...path]` proxies an explicit allowlist of contact operations
  (`/contacts*`, `/consents/{id}/revoke`, `/search`) for client components, forwarding
  `If-Match` and relaying `ETag`.

## Screens

| Path | Content |
| --- | --- |
| `/anmelden`, `/anmelden/zweiter-faktor` | e-mail and password, then TOTP (first login: QR code and secret) |
| `/mandant` | tenant selection when the account has several tenants |
| `/kontakte` | server rendered list with search `q`, filters `kind` and `tag`, pagination (25 per page) |
| `/kontakte/neu` | form for person or company with repeatable addresses, phones, e-mails, bank accounts; duplicate check before saving |
| `/kontakte/[id]` | tabs Stammdaten, Kommunikation, Bankverbindungen (masked IBAN only), Notizen, Einwilligungen; actions Bearbeiten, DSGVO-Auskunft, Löschen |
| `/kontakte/[id]/bearbeiten` | `PUT` with `If-Match`; 412 shows a German conflict message |

The header holds the tenant switcher, the global search (Strg+K or Cmd+K, `/api/v1/search`) and
the user menu with logout. Forms use react-hook-form with zod rules mirroring `ContactIn`
(`src/lib/contact-schema.ts`); the API stays authoritative, its problem details are shown in
German and field errors are mapped to the form fields (`src/lib/problem.ts`).

Editing a contact omits `bank_accounts`, so the API keeps them (they are only delivered
masked and may be referenced by SEPA mandates). Changing bank accounts needs its own flow
(planned together with the four-eyes rule for IBAN changes).

## E2E against the API

`scripts/e2e-backend.sh` expects a bootstrapped PostgreSQL (`make db-bootstrap`) and Redis. It
migrates, generates throwaway `MHVP_MASTER_KEY`/`MHVP_JWT_PRIVATE_KEY` when unset, seeds a fresh
admin (`MHVP_SEED_ADMIN_EMAIL`, default `e2e-<time>-<pid>@example.org`, random password), starts
the API on port 8000 (`MHVP_E2E_API_PORT`), builds the CRM and runs Playwright with
`E2E_BACKEND=1`. The test logs in, computes the TOTP code from the secret on the setup page
(`otpauth`), selects "Hausverwaltung Müller GmbH", creates a contact, finds it via list search
and Strg+K, edits and deletes it. The API log is written to `playwright-report-api.log`.
Defaults match the local dev database (`mhvp_app`/`dev-app`, `mhvp_migrator`/`dev-migrator`).
CI runs the same script in the `e2e-backend` job.
