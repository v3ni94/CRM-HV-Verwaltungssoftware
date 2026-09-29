# ADR 0016: CRM as an installable shell without a data cache

- Status: Accepted (operator decision M30-08 of 28.09.2026; product protection, no legal duty)
- Date: 2026-09-29

## Context

Master prompt section 3.1 defines only the portal as a progressive web app; the CRM was a
plain browser application. Property managers record handovers, tickets and meter readings
on site with a tablet or a phone (plan `docs/plans/M31-handy-tablet.md`, work package WP5).
On an iPad or an Android phone a home screen entry in full screen removes the browser chrome,
keeps the app one tap away and prevents the accidental loss of a form through the address
bar. Two risks stood against it: a service worker that caches API responses, pages or
documents would store personal and financial data on a possibly shared device (rule 0.1.3,
0.1.13), and the middleware matcher of the CRM was narrowed on purpose after the operator
report of 28.09.2026 (every page and API path behind the session), so the files a service
worker needs (`sw.js`, `offline.html`, `manifest.webmanifest`, icons) were redirected to the
login page. The operator released the shell and the matcher exception on 28.09.2026
(decision M30-08).

## Decision

1. The CRM ships a web app manifest (`apps/web-crm/src/app/manifest.ts`: name MH
   Verwaltungsplattform, short name MHVP, id and start URL `/start`, display standalone,
   shortcuts Übergabeprotokolle, Kalender, Tickets), icons 192 and 512 `any` plus 512
   `maskable` generated from the existing brand mark `public/marke-mhag.png` on the day
   background token, and a static offline page `public/offline.html` in German.
2. The service worker `public/sw.js` caches exactly the offline page and the icons.
   Navigations are network first with a timeout of 8 seconds, then the offline page. Requests
   to `/api/`, pages, documents and every other resource are never cached and never answered
   from the cache. The cache name carries the release; activation deletes older caches.
3. The middleware matcher and the `PUBLIC` list of `apps/web-crm/src/middleware.ts` are
   widened by exactly `sw.js`, `offline.html`, `manifest.webmanifest` and PNG files directly
   under `icons/`. Every page and every API path stays behind the session
   (`src/middleware.test.ts`).
4. The install hint is an entry Als App installieren in the user menu, never a banner. A
   remembered `beforeinstallprompt` opens the browser prompt; iPhone and iPad (including
   iPadOS reporting itself as a Mac with touch points) show the Safari steps once. A dismissal
   is remembered in the browser only and tolerates a blocked storage.
5. `<meta name="theme-color">` follows the active theme: `src/lib/theme.ts` reads
   `--mhvp-color-bg` of the current `data-theme` from `getComputedStyle` and observes the
   attribute, so the status bar of the installed app changes with day and evening without a
   hex value in code. The manifest keeps a documented hex copy of the day token because a
   manifest cannot read CSS (`src/app/manifest.test.ts` guards the copy).
6. Nothing in the shell stores form data, photos, signatures or drafts on the device; offline
   recording stays an open operator decision (M30-07).

## Consequences

- Links that open a new tab (`target="_blank"`) lose the session of an installed iOS app in
  the external tab. WP5 removed them from the portal protocol; the CRM still has 29
  occurrences in 20 files (list in the pull request of WP5). They are to be reviewed per case
  in a follow up (same tab, download or a sheet), starting with the handover editor.
- Tests: `src/middleware.test.ts` (shell files open, pages and API locked, neighbours such as
  `/icons/x.svg` locked), `src/components/shell/InstallHint.test.tsx`, `src/lib/theme.test.ts`
  (meta follows `data-theme`), `src/app/manifest.test.ts`, `e2e/pwa.spec.ts` (manifest, icons,
  worker registration, offline page, session lock).
- Acceptance by the operator on Android Chrome and iPad Safari: install, start on `/start`
  in full screen without a colour jump, evening status bar, offline page without network,
  Cache Storage without API responses or documents.
- Releases must bump the cache name in `public/sw.js` (integrator, together with the
  version), otherwise an old offline page or icon stays in the cache of installed apps.

## Alternatives considered

- No CRM shell (portal only, as in section 3.1): rejected by the operator for on site work.
- Runtime caching of pages or API responses for an offline mode: rejected, personal and
  financial data on a shared device, rule 0.1.3 and 0.1.13; open decision M30-07.
- Wider middleware exception (`public/` as a whole or every `.js`): rejected, the matcher
  stays as narrow as the shell needs.
- Install banner on every page: rejected, noise on shared devices; the user menu entry is
  enough.

## References

- `docs/MASTER-PROMPT.md` section 3.1 (portal as PWA), 0.1.3, 0.1.13
- `docs/plans/M31-handy-tablet.md` WP5, operator decisions 5 (M30-08) and 1 (M30-07)
- `docs/ASSUMPTIONS.md` A-084
- ADR 0013 (responsive primitives)
