# @mhvp/web-portal

Next.js 15 (App Router) app of the MH Verwaltungsplattform: portals for tenants, owners and service providers (production hosts `portal.muellerhv.de`, `portal.mueller-holding.ag`). Delivered so far: the skeleton (M1) and the
handover protocols of a participant (M30 stage 3, `docs/plans/M30-uebergabeprotokoll.md`): sign-in with
password and second factor (`/anmelden`, same httpOnly cookie session as the CRM app, `src/lib/session.ts`),
`/uebergabe` (own protocols), `/uebergabe/[id]` (sections, photos, signature, completion). JSON calls go
through `/api/bff/[...path]` (allowlist of `/api/v1/portal/handover*`), binaries through `/api/portal-files`.

## Commands

| Command | Does |
| --- | --- |
| `pnpm --filter @mhvp/web-portal dev` | dev server on port 3001 |
| `pnpm --filter @mhvp/web-portal build` / `start` | production build and server (port 3001) |
| `pnpm --filter @mhvp/web-portal lint` | ESLint, no warnings allowed |
| `pnpm --filter @mhvp/web-portal typecheck` | `tsc --noEmit` |
| `pnpm --filter @mhvp/web-portal test` | Vitest component and route tests |
| `pnpm --filter @mhvp/web-portal e2e` | Playwright smoke tests in all projects (`chromium`, `phone`, `tablet`, `tablet-landscape`; `@backend` specs need `scripts/e2e-backend.sh`) |

In the Compose dev stack the app is served at `http://portal.localhost`.

## Tests on phone and tablet viewports (M31 WP4)

Same layout as the CRM (`apps/web-crm/README.md`): the projects `phone` (390x844), `tablet`
(820x1180) and `tablet-landscape` (1024x768) run only the specs tagged `@mobile` with a coarse
pointer; `chromium` runs the rest. `e2e/mobile-layout.ts` holds the assertions,
`e2e/shell.mobile.spec.ts` checks home and login without a backend, and
`e2e/handover.mobile.backend.spec.ts` (`@backend @mobile`) the helper path: menu entry
Übergabe, protocol without overflow, camera and gallery inputs, signature canvas. Source guards:
`src/lib/table-wrapper.test.ts` and `src/lib/no-fixed-width.test.ts`. Safari and iPadOS are
checked by hand (`docs/acceptance/M31-geraetepruefung.md`).

## Contract (`docs/plans/M1.md` section 4.5)

- `GET /api/health` returns `{"status": "ok", "service": "web-portal", "version": "<semver>"}`.
- The German home page shows the product name and a server rendered API status line using
  `@mhvp/api-client` against `MHVP_API_INTERNAL_URL` + `/api/v1/health/ready`.
- i18n with next-intl, default `de-DE`. No invented CI colours or logos: neutral tokens from
  `@mhvp/ui` until the CI values are released (V14, OPEN_QUESTIONS M1-08).
- Appearance: day and evening mode on the shared tokens (`docs/design/tokens.md`). Default is
  automatic (operating system preference, followed live); the header switch Hell, Dunkel,
  Automatisch stores the choice in localStorage (`mhvp-portal-theme`) only, portal accounts
  have no preference endpoint. The inline script in `src/app/layout.tsx` sets `data-theme`
  before the first paint; `public/offline.html` reads the same key.
- All data access goes through the documented API (rule 0.1.4).
- Languages (GB14-01): the list is derived from the files `messages/<code>.json` (`next.config.ts`
  sets `NEXT_PUBLIC_PORTAL_LOCALES` at build time, `src/lib/locale.ts` reads it, German always
  stays available). A further language is a new file plus the same code in `MHVP_PORTAL_LOCALES`
  of the API (validation of `PATCH /portal/me/locale`); missing keys fall back to German
  (`src/i18n/request.ts`). Language names come from `Intl.DisplayNames`.
- Maintenance banner (GB16-01): `src/components/shell/MaintenanceBanner.tsx` reads the public feed
  `GET /api/v1/platform/maintenance/current` (cached 30 seconds, no banner on failure).
- Legal texts of the tenant (AE29, M21-04): public page `/rechtliches/<impressum|datenschutz|nutzungsbedingungen>`
  (middleware public, `src/lib/legal-texts.ts` reads `GET /api/v1/tenant/legal-texts/{code}` by portal host,
  `LegalTextView` renders the approved text as plain text or the marker "Text nicht freigegeben").
  Footer and sign-in links (`legalLinks` in `src/lib/branding.ts`): released text first, else the https link of
  the branding, else none. The branding answer carries `legal_texts_released`.
