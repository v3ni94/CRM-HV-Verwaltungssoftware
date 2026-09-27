/** Shared Tailwind class sets on the @mhvp/ui tokens (docs/design/tokens.md). Colour only as
 *  meaning: accent marks interactive state (focus, hover, markers), primary actions are neutral,
 *  cards use hairlines without shadows, numbers use tabular figures. */
export const ui = {
  input:
    "w-full min-h-11 rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg placeholder:text-subtle transition-shadow duration-150 focus:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-focus sm:min-h-10",
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border bg-bg px-3 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:min-h-10",
  primary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-fg transition duration-150 hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 disabled:opacity-50 sm:min-h-10",
  secondary:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:min-h-10",
  danger:
    "inline-flex min-h-11 items-center gap-1.5 rounded-md bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50 sm:min-h-10",
  formActions: "flex w-full flex-col gap-2 sm:w-auto sm:flex-row",
  actionFull: "w-full justify-center sm:w-auto",
  buttonSm:
    "inline-flex min-h-9 items-center gap-1 rounded-md border border-border bg-bg px-2.5 py-1 text-xs font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface focus:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50",
  alert: "rounded-md border border-danger-line bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-line bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-accent bg-surface px-3 py-2 text-sm text-muted",
  card: "rounded-lg border border-hairline bg-bg p-4 sm:p-5",
  cardLift: "mhvp-lift rounded-lg border border-hairline bg-bg p-4 sm:p-5",
  cardLink:
    "mhvp-lift block rounded-lg border border-hairline bg-bg p-4 transition duration-150 hover:border-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-focus sm:p-5",
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
  pageGap: "flex flex-col gap-6",
  sectionGap: "flex flex-col gap-4",
  badge: "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-muted",
  badgeGold: "inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-fg",
  badgeSuccess: "inline-flex items-center gap-1.5 rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success-fg",
  badgeWarning: "inline-flex items-center gap-1.5 rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning-fg",
  badgeInfo: "inline-flex items-center gap-1.5 rounded-full bg-info-bg px-2.5 py-0.5 text-xs font-medium text-info-fg",
  info: "rounded-md border border-info-line bg-info-bg px-3 py-2 text-sm text-info-fg",
  warning: "rounded-md border border-warning-line bg-warning-bg px-3 py-2 text-sm text-warning-fg",
  badgeDanger: "inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-xs font-medium text-danger-fg",
} as const;
