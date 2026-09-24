/** Shared Tailwind class sets on the @mhvp/ui tokens. Gold is an accent (focus, markers,
 *  active states), primary actions are anthracite; no other colours are introduced (CI). */
export const ui = {
  input:
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg placeholder:text-subtle transition-shadow duration-150 focus:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40",
  label: "block text-xs font-medium text-muted",
  help: "text-xs text-subtle",
  error: "text-xs text-danger-fg",
  button:
    "inline-flex items-center gap-1.5 rounded-md border border-border bg-bg px-3 py-2 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  primary:
    "inline-flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-fg shadow-xs transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/60 focus:ring-offset-2 disabled:opacity-50",
  secondary:
    "inline-flex items-center gap-1.5 rounded-md border border-fg/20 bg-transparent px-3.5 py-2 text-sm font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  danger:
    "inline-flex items-center gap-1.5 rounded-md bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition duration-150 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  buttonSm:
    "inline-flex items-center gap-1 rounded-md border border-border bg-bg px-2.5 py-1 text-xs font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  alert: "rounded-md border border-danger-fg/20 bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  success: "rounded-md border border-success-fg/20 bg-success-bg px-3 py-2 text-sm text-success-fg",
  notice: "rounded-md border-l-2 border-gold bg-surface px-3 py-2 text-sm text-muted",
  card: "rounded-xl border border-border bg-bg p-5 shadow-card",
  cardLift: "mhvp-lift rounded-xl border border-border bg-bg p-5 shadow-card",
  cardLink:
    "mhvp-lift block rounded-xl border border-border bg-bg p-5 shadow-card transition duration-150 hover:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40",
  title: "mhvp-title text-2xl font-semibold tracking-tight",
  h2: "mhvp-h2 font-semibold text-fg",
  subtitle: "mhvp-label",
  table: "mhvp-table",
  badge: "inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-0.5 text-xs font-medium text-muted",
  badgeGold: "inline-flex items-center gap-1.5 rounded-full bg-gold-soft px-2.5 py-0.5 text-xs font-medium text-fg",
  badgeSuccess: "inline-flex items-center gap-1.5 rounded-full bg-success-bg px-2.5 py-0.5 text-xs font-medium text-success-fg",
  badgeWarning: "inline-flex items-center gap-1.5 rounded-full bg-warning-bg px-2.5 py-0.5 text-xs font-medium text-warning-fg",
  badgeDanger: "inline-flex items-center gap-1.5 rounded-full bg-danger-bg px-2.5 py-0.5 text-xs font-medium text-danger-fg",
} as const;
