# ADR 0013: Responsive primitives for phone and tablet use of the CRM

- Status: Accepted (operator plan M31, 28.09.2026; product protection, no legal duty)
- Date: 2026-09-28

## Context

The CRM was laid out for a desktop with a mouse: the rail appeared from `md` (768 px), so a
tablet in portrait lost a quarter of its width to the navigation; the header wrapped to two
rows; controls shrank to 40 px from `sm` regardless of the pointer; `main` hid overflow, so
wide tables were cut off silently; every dialog and confirmation was either `window.confirm`
or ad hoc portal code. Property managers record handovers, tickets and meter readings on
site with a tablet or a phone (plan `docs/plans/M31-handy-tablet.md`, work packages WP1 to
WP5). The plan fixes the interfaces of the shared building blocks in WP1 so that the editor
(WP2) and the data pages (WP3) can be built in parallel worktrees against them.

Constraints: master prompt rule 0.1.12 (small traceable changes, no unrequested
refactoring), rule 0.1.3 (no local storage of protocol data, photos or signatures as a data
protection risk), the lock zone `apps/web-crm/src/components/ai/*` (AI launcher in the lower
right corner, untouched by any package), Tailwind 4.3.3 (built in `pointer-coarse` and
`pointer-fine` variants), and the requirement that a desktop with a mouse at 1280 px and more
looks the same as before.

## Decision

1. Styled primitives live in the CRM, `packages/ui` stays headless. Tailwind scans only the
   sources of each app, so class sets in a shared package would not be emitted. The CRM owns
   `apps/web-crm/src/lib/ui.ts` (class sets `tableScroll`, `tableCard`, `cardsMobile`,
   `tabBar`, `tab`, `tabActive`, `segment`, `segmentActive`, `iconButton`, `bottomBar`) and
   the components `ResponsiveList`, `KeyValueList`, `Sheet`, `ConfirmSheet` with
   `useConfirm()`, `BottomBar` under `apps/web-crm/src/components/ui/`, plus the hooks
   `useMediaQuery` and `useOnline` under `apps/web-crm/src/lib/`. `packages/ui` keeps only
   CSS (tokens, theme, base), the theme mode core and, from WP2, the headless signature
   canvas. The portal keeps a twin of the class sets in `apps/web-portal/src/lib/ui.ts`
   (WP5 adds `tabBar`, `tab`, `tabActive`, `bottomBar` there); the twin is a deliberate
   duplication of strings, not of logic.
2. Target sizes follow the pointer, not the width. Controls are 44 px everywhere and shrink
   only from `sm` with a fine pointer (`min-h-11 sm:pointer-fine:min-h-10`). We use the
   variants Tailwind 4.3.3 ships and decide against `@custom-variant` aliases (`coarse:`,
   `touch:`): an alias hides which media query is meant, needs a build side definition in
   both apps and would break the moment the built in name is used next to it. `ui.test.ts`
   pins the class sets and rejects a bare `sm:min-h-10`.
3. Three device tiers and one rail decision. The shell becomes a row at `lg`, the rail is an
   icon rail of 4.5 rem from `lg` and the full rail of 16 rem from `xl`, rendered purely by
   CSS in the `auto` mode (no `matchMedia`, no jump after hydration). Manual modes
   `expanded` and `collapsed` stay a per browser preference under the existing localStorage
   key (the only stored shell flag; the old boolean is parsed tolerantly) and are announced
   as `data-rail` on `html` so the fixed `BottomBar` can follow the rail edge in CSS. The
   drawer serves phones and tablets and the icon rail (window event `mhvp:open-nav`), shares
   the server side group state (`useNavGroups`, `PATCH nav_expanded_groups`) and the query
   aware active check (`useActiveHref`) with the rail.
4. Nothing is cut off silently. `main` uses `overflow-x-clip`; every data table is rendered
   through `ResponsiveList`, `ui.tableScroll` or `ui.tableCard` (WP3 sweeps the existing
   tables, WP4 adds a source scan and element wise overflow checks in Playwright).
5. Layout by CSS, behaviour by hooks. `Sheet` positions itself with `md:` variants (bottom
   sheet below `md`, centred card from `md`); `useMediaQuery` is reserved for behaviour such
   as autofocus or a phone only flow and is `false` on the server and the first render.
6. No local persistence beyond the rail flag. `Sheet`, `ConfirmSheet`, `useOnline` and the
   drawer keep nothing in `localStorage`, IndexedDB or a service worker; `useOnline` is a hint
   and never a proof that a request succeeded.

## Consequences

- Desktop with a mouse at 1280 px and more is unchanged apart from the header height
  (64 px instead of the former 63 px wrapped row). Table heads keep `top: 0` of their scroll
  container; only a table with `ui.tablePage` (`mhvp-table--page`, no scroll wrapper) sticks
  below the header via `--mhvp-sticky-top`, which the CRM sets to `--mhvp-header-h` in its
  `globals.css` while the portal keeps `0px` (review after WP1: an offset inside an
  `overflow-x: auto` wrapper shifts the head over the first rows at scroll position 0).
- Tablets with touch get 44 px controls even above `sm`; phones get 16 px inputs.
- WP2 and WP3 build only against the interfaces listed in `docs/design/README.md`
  ("Handy und Tablet") and this ADR; new pages never invent their own class chains.
- Tests: `ui.test.ts`, one vitest file per primitive and hook, `SideNav.test.tsx`,
  `MobileNav.test.tsx`, `CommandPalette.test.tsx`, `NotificationBell.test.tsx`,
  `UserMenu.test.tsx`, `StatusChip.test.tsx`, `InlineField.test.tsx`; the portal test suite
  runs after every change to `packages/ui` because both apps import the CSS.
- Open (operator, no gate affected): whether the portal should adopt the CRM primitives as
  code instead of string twins. The sticky offset question is settled: the portal has no
  sticky header and keeps `--mhvp-sticky-top: 0px`.

## Alternatives considered

- Styled components in `packages/ui`: rejected, Tailwind would not emit their classes for
  the apps without a content configuration that scans the package, and the package would
  take a dependency on the apps' theme mapping.
- `@custom-variant touch (@media (pointer: coarse))`: rejected, see decision 2.
- A JavaScript rail decision with `matchMedia`: rejected, it renders the wrong width on the
  server and jumps after hydration; CSS variants are deterministic on the first paint.
- A React context for confirmations (`ConfirmProvider` in the layout): rejected for now, the
  hook returning a node works in any client component and in component tests without a
  provider; a provider can be added later without changing the call sites.
- `md` as the rail breakpoint with a narrower rail: rejected, a 768 px tablet in portrait
  needs the full width for two column forms and tables.

## References

- `docs/plans/M31-handy-tablet.md` (summary, principles, WP1 to WP5)
- `docs/design/README.md` section "Handy und Tablet", `docs/design/tokens.md` section
  "Handy und Tablet (M31)"
- `docs/MASTER-PROMPT.md` rules 0.1.3, 0.1.9, 0.1.12; ADR 0012 (inline editing, pencil
  button)
- `apps/web-crm/src/lib/ui.ts`, `apps/web-crm/src/components/ui/`, `packages/ui/src/`
