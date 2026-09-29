/** Shared Tailwind class sets on the @mhvp/ui tokens (docs/design/tokens.md). Colour only as
 *  meaning: accent marks interactive state (focus, hover, markers), primary actions are neutral,
 *  numbers use tabular figures. Surfaces follow the 1.37 roles: page ground `bg`, cards
 *  `surface` (soft shadow by day, 1px line in the evening), subtle fills `surface-2`, floating
 *  layers `raised`, form fields `field-bg` with `field-line`.
 *
 *  Target sizes follow the pointer, not the width (M31, docs/design/README.md "Handy und
 *  Tablet"): controls are 44 px (`min-h-11`) everywhere and shrink to 40 px only from `sm`
 *  with a fine pointer (`sm:pointer-fine:min-h-10`, Tailwind built in variants, no
 *  `@custom-variant`). Breakpoints: below `sm` phone, `sm` tablet, `lg` desktop with icon
 *  rail, `xl` full rail. Inputs use 16 px text below `sm` against the iOS focus zoom. The
 *  portal keeps its own twin in apps/web-portal/src/lib/ui.ts (ADR 0013). */
const focusRing = "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus";
const cardBase = "mhvp-surface-card rounded-lg border border-card-line bg-surface";

export const ui = {
  input:
    `w-full min-h-11 rounded-md border border-field-line bg-field-bg px-3 py-2 text-base text-fg placeholder:text-subtle transition duration-150 hover:border-fg/50 focus:border-accent-strong ${focusRing} disabled:cursor-not-allowed disabled:opacity-60 sm:pointer-fine:min-h-10 sm:text-sm`,
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium text-fg shadow-xs transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50 sm:pointer-fine:min-h-10`,
  primary:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-fg shadow-xs transition duration-150 hover:bg-primary-hover ${focusRing} focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-50 sm:pointer-fine:min-h-10`,
  secondary:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50 sm:pointer-fine:min-h-10`,
  danger:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-danger-line bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:border-danger-fg ${focusRing} disabled:opacity-50 sm:pointer-fine:min-h-10`,
  formActions: "flex w-full flex-col gap-2 sm:w-auto sm:flex-row",
  actionFull: "w-full justify-center sm:w-auto",
  buttonSm:
    `inline-flex min-h-9 items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs pointer-coarse:min-h-11 pointer-coarse:px-3 font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50`,
  alert: "rounded-md border border-danger-line bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-line bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-accent bg-surface-2 px-3 py-2 text-sm text-muted",
  card: `${cardBase} p-4 shadow-card sm:p-5`,
  /** Card without padding around a data table: the table scrolls horizontally inside the card
   *  instead of pushing the page (M31). Composed from the card base so no `p-4` competes with
   *  `p-0` (Tailwind orders `p-0` before `p-4`). */
  tableCard: `${cardBase} overflow-x-auto p-0 shadow-card`,
  /** Bleeding scroll wrapper for a table on the page ground: full width on phones (negative
   *  page gutter), plain block from `sm`. */
  tableScroll: "-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0",
  /** Card list shown below `sm` in place of a table (`ResponsiveList`). */
  cardsMobile: "flex flex-col gap-2 sm:hidden",
  /** Step or section bar: one swipeable row on phones (snap points, hidden scrollbar), wrapping
   *  from `sm`. Items use `tab` and `tabActive`. */
  tabBar: "-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] snap-x scroll-px-4 sm:mx-0 sm:flex-wrap sm:px-0",
  tab: `shrink-0 snap-start inline-flex min-h-11 items-center gap-1.5 rounded-full px-3.5 text-sm font-medium text-muted transition duration-150 hover:bg-surface-2 hover:text-fg ${focusRing}`,
  tabActive: `shrink-0 snap-start inline-flex min-h-11 items-center gap-1.5 rounded-full bg-accent-soft px-3.5 text-sm font-semibold text-fg ${focusRing}`,
  /** Segmented control (for example month or week): equal width options in a flex row. */
  segment: `inline-flex min-h-11 flex-1 items-center justify-center rounded-md border border-border bg-surface px-3 text-sm font-medium text-muted transition duration-150 hover:border-accent hover:text-fg ${focusRing} sm:pointer-fine:min-h-10`,
  segmentActive: `inline-flex min-h-11 flex-1 items-center justify-center rounded-md border border-accent bg-accent-soft px-3 text-sm font-semibold text-fg ${focusRing} sm:pointer-fine:min-h-10`,
  /** Square icon button: 44 px on every device with a coarse pointer, 36 px with a mouse from
   *  `sm`. */
  iconButton: `inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-muted transition duration-150 hover:bg-surface-2 hover:text-fg ${focusRing} sm:pointer-fine:h-9 sm:pointer-fine:w-9`,
  /** Sticky action row at the bottom of a form panel on phones (safe area, `pr-20` keeps the
   *  corner of the AI launcher free); a plain row from `sm`. For a viewport fixed bar use the
   *  `BottomBar` component. */
  bottomBar:
    "sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center gap-2 border-t border-border-soft bg-bg px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pr-20 sm:static sm:z-auto sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0",
  cardLift: "mhvp-surface-card mhvp-lift rounded-lg border border-card-line bg-surface p-4 shadow-card sm:p-5",
  cardLink:
    `mhvp-surface-card mhvp-lift block rounded-lg border border-card-line bg-surface p-4 shadow-card transition duration-150 hover:border-accent ${focusRing} sm:p-5`,
  /** Floating layer (menu, popover, dropdown): raised surface, line, shadow by day. */
  popover: "rounded-lg border border-border bg-raised text-fg shadow-lg",
  /** Modal backdrop. */
  scrim: "bg-scrim",
  title: "mhvp-title font-semibold text-fg",
  h2: "mhvp-h2 font-semibold text-fg",
  h3: "mhvp-h3 font-semibold text-fg",
  display: "mhvp-display text-fg",
  small: "mhvp-small text-muted",
  /** Numbers and amounts: tabular figures, right aligned in tables via the `num` cell class. */
  num: "mhvp-num",
  mono: "mhvp-mono",
  subtitle: "mhvp-label",
  table: "mhvp-table",
  /** Table that scrolls with the page (no scroll wrapper): its head sticks below the app
   *  header via `--mhvp-sticky-top`. Inside `tableScroll`, `tableCard` or `ResponsiveList`
   *  use `table`, the wrapper is the scroll container there and any offset would push the head
   *  over the first rows (M31 review). */
  tablePage: "mhvp-table mhvp-table--page",
  pageGap: "flex flex-col gap-6",
  sectionGap: "flex flex-col gap-4",
  badge: "inline-flex items-center gap-1.5 rounded-full bg-muted-bg px-2.5 py-0.5 text-xs font-semibold text-muted-fg",
  badgeGold: "inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-fg",
  badgeSuccess: "inline-flex items-center gap-1.5 rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-semibold text-success-fg",
  badgeWarning: "inline-flex items-center gap-1.5 rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-semibold text-warning-fg",
  badgeInfo: "inline-flex items-center gap-1.5 rounded-full bg-info-bg px-2.5 py-0.5 text-xs font-semibold text-info-fg",
  info: "rounded-md border border-info-line bg-info-bg px-3 py-2 text-sm text-info-fg",
  warning: "rounded-md border border-warning-line bg-warning-bg px-3 py-2 text-sm text-warning-fg",
  badgeDanger: "inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-xs font-semibold text-danger-fg",
} as const;
