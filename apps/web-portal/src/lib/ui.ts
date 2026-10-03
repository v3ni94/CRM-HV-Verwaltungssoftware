/** Shared Tailwind class sets on the @mhvp/ui tokens (docs/design/tokens.md). Touch targets stay
 *  44 px on every device with a coarse pointer (Tailwind `pointer-fine` variant, M31); inputs use
 *  16 px below `sm` against the iOS focus zoom. Colour only as
 *  meaning: accent marks interactive state (focus, hover, markers), primary actions are neutral,
 *  cards use hairlines without shadows, numbers use tabular figures. */
export const ui = {
  input:
    "w-full min-h-11 rounded-md border border-field-line bg-field-bg px-3 py-2 text-base text-fg placeholder:text-subtle transition-shadow duration-150 focus:border-accent-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-focus sm:pointer-fine:min-h-10 sm:text-sm",
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:pointer-fine:min-h-10",
  primary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-fg transition duration-150 hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 disabled:opacity-50 sm:pointer-fine:min-h-10",
  secondary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:pointer-fine:min-h-10",
  danger:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:pointer-fine:min-h-10",
  formActions: "flex w-full flex-col gap-2 sm:w-auto sm:flex-row",
  actionFull: "w-full justify-center sm:w-auto",
  buttonSm:
    "inline-flex min-h-11 items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 pointer-fine:min-h-9",
  alert: "rounded-md border border-danger-line bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-line bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-accent bg-surface-2 px-3 py-2 text-sm text-muted",
  card: "mhvp-surface-card rounded-lg border border-card-line bg-surface p-4 shadow-card sm:p-5",
  cardLift: "mhvp-surface-card mhvp-lift rounded-lg border border-hairline bg-surface p-4 sm:p-5",
  cardLink:
    "mhvp-lift block rounded-lg border border-hairline bg-surface p-4 transition duration-150 hover:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-focus sm:p-5",
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
  /** Wrapper for data tables: horizontal scrolling on narrow screens instead of page overflow. */
  tableScroll: "-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0",
  tableStickyCol: "mhvp-table--sticky-col",
  /** Section bar of the handover protocol (M31 WP5, twin of the CRM class set): one swipeable
   *  row on phones (snap points, hidden scrollbar), wrapping from `sm`. Items use `tab` and
   *  `tabActive`, both 44 px high. */
  tabBar: "-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] snap-x scroll-px-4 sm:mx-0 sm:flex-wrap sm:px-0",
  tab: "shrink-0 snap-start inline-flex min-h-11 items-center gap-1.5 rounded-full px-3.5 text-sm font-medium text-muted transition duration-150 hover:bg-surface-2 hover:text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus",
  tabActive:
    "shrink-0 snap-start inline-flex min-h-11 items-center gap-1.5 rounded-full bg-accent-soft px-3.5 text-sm font-semibold text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-focus",
  /** Sticky action row at the bottom of a form on phones (safe area of the home indicator), a
   *  plain row from `sm`. */
  bottomBar:
    "sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center gap-2 border-t border-border bg-bg px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:static sm:z-auto sm:mx-0 sm:border-0 sm:bg-transparent sm:p-0",
  srOnly: "sr-only",
  pageGap: "flex flex-col gap-6",
  sectionGap: "flex flex-col gap-4",
  badge: "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-xs font-medium text-muted",
  badgeGold: "inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-fg",
  badgeSuccess: "inline-flex items-center gap-1.5 rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success-fg",
  badgeWarning: "inline-flex items-center gap-1.5 rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning-fg",
  badgeInfo: "inline-flex items-center gap-1.5 rounded-full bg-info-bg px-2.5 py-0.5 text-xs font-medium text-info-fg",
  info: "rounded-md border border-info-line bg-info-bg px-3 py-2 text-sm text-info-fg",
  warning: "rounded-md border border-warning-line bg-warning-bg px-3 py-2 text-sm text-warning-fg",
  badgeDanger: "inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-xs font-medium text-danger-fg",
} as const;
