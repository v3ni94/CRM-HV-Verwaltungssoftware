/** Shared Tailwind class sets on the @mhvp/ui tokens (docs/design/tokens.md). Colour only as
 *  meaning: accent marks interactive state (focus, hover, markers), primary actions are neutral,
 *  numbers use tabular figures. Surfaces follow the 1.37 roles: page ground `bg`, cards
 *  `surface` (soft shadow by day, 1px line in the evening), subtle fills `surface-2`, floating
 *  layers `raised`, form fields `field-bg` with `field-line`. */
const focusRing = "focus:outline-none focus-visible:ring-2 focus-visible:ring-focus";

export const ui = {
  input:
    `w-full min-h-11 rounded-md border border-field-line bg-field-bg px-3 py-2 text-sm text-fg placeholder:text-subtle transition duration-150 hover:border-fg/50 focus:border-accent-strong ${focusRing} disabled:cursor-not-allowed disabled:opacity-60 sm:min-h-10`,
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium text-fg shadow-xs transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50 sm:min-h-10`,
  primary:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-fg shadow-xs transition duration-150 hover:bg-primary-hover ${focusRing} focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:opacity-50 sm:min-h-10`,
  secondary:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50 sm:min-h-10`,
  danger:
    `inline-flex min-h-11 items-center gap-1.5 rounded-md border border-danger-line bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:border-danger-fg ${focusRing} disabled:opacity-50 sm:min-h-10`,
  formActions: "flex w-full flex-col gap-2 sm:w-auto sm:flex-row",
  actionFull: "w-full justify-center sm:w-auto",
  buttonSm:
    `inline-flex min-h-9 items-center gap-1 rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-medium text-fg transition duration-150 hover:border-accent hover:bg-surface-2 ${focusRing} disabled:opacity-50`,
  alert: "rounded-md border border-danger-line bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-line bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-accent bg-surface-2 px-3 py-2 text-sm text-muted",
  card: "mhvp-surface-card rounded-lg border border-card-line bg-surface p-4 shadow-card sm:p-5",
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
