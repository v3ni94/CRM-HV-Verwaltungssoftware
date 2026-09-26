/** Shared Tailwind class sets on the @mhvp/ui tokens. Gold is an accent (focus, markers,
 *  active states), primary actions are anthracite; no other colours are introduced (CI). */
export const ui = {
  input:
    "w-full min-h-11 rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg placeholder:text-subtle transition-shadow duration-150 focus:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40 sm:min-h-10",
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border bg-bg px-3 py-2 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50 sm:min-h-10",
  primary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-fg shadow-xs transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/60 focus:ring-offset-2 disabled:opacity-50 sm:min-h-10",
  secondary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50 sm:min-h-10",
  danger:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50 sm:min-h-10",
  formActions: "flex w-full flex-col gap-2 sm:w-auto sm:flex-row",
  actionFull: "w-full justify-center sm:w-auto",
  buttonSm:
    "inline-flex min-h-9 items-center gap-1 rounded-md border border-border bg-bg px-2.5 py-1 text-xs font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  alert: "rounded-md border border-danger-fg/20 bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-fg/20 bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-gold bg-surface px-3 py-2 text-sm text-muted",
  card: "rounded-xl border border-border bg-bg p-4 shadow-card sm:p-5",
  cardLift: "mhvp-lift rounded-xl border border-border bg-bg p-4 shadow-card sm:p-5",
  cardLink:
    "mhvp-lift block rounded-xl border border-border bg-bg p-4 shadow-card transition duration-150 hover:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40 sm:p-5",
  title: "mhvp-title text-2xl font-semibold tracking-tight",
  h2: "mhvp-h2 font-semibold text-fg",
  subtitle: "mhvp-label",
  table: "mhvp-table",
  /** Wrapper for data tables: horizontal scrolling on narrow screens instead of page overflow. */
  tableScroll: "-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0",
  tableStickyCol: "mhvp-table--sticky-col",
  srOnly: "sr-only",
  pageGap: "flex flex-col gap-6",
  sectionGap: "flex flex-col gap-4",
  badge: "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-muted",
  badgeGold: "inline-flex items-center gap-1.5 rounded-full bg-gold-soft px-2.5 py-0.5 text-xs font-medium text-fg",
  badgeSuccess: "inline-flex items-center gap-1.5 rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success-fg",
  badgeWarning: "inline-flex items-center gap-1.5 rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning-fg",
  badgeDanger: "inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-xs font-medium text-danger-fg",
} as const;
