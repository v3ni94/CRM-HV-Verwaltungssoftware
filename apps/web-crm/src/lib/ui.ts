/** Shared Tailwind class sets on the @mhvp/ui tokens. Gold is an accent (focus, markers,
 *  active states), primary actions are anthracite; no other colours are introduced (CI). */
export const ui = {
  input:
    "w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg placeholder:text-subtle transition focus:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40",
  label: "block text-xs font-medium text-muted",
  button:
    "inline-flex items-center gap-1.5 rounded-md border border-border bg-bg px-3 py-2 text-sm font-medium text-fg transition hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  primary:
    "inline-flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-fg transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/60 focus:ring-offset-2 disabled:opacity-50",
  danger:
    "inline-flex items-center gap-1.5 rounded-md bg-danger-bg px-3.5 py-2 text-sm font-medium text-danger-fg transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/40 disabled:opacity-50",
  error: "text-xs text-danger-fg",
  alert: "rounded-md border border-danger-fg/20 bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  notice: "rounded-md border-l-2 border-gold bg-surface px-3 py-2 text-sm text-muted",
  card: "rounded-xl border border-border bg-bg p-5 shadow-card",
  cardLink:
    "block rounded-xl border border-border bg-bg p-5 shadow-card transition hover:border-gold hover:shadow-md focus:outline-none focus:ring-2 focus:ring-gold/40",
  title: "mhvp-title text-2xl font-semibold tracking-tight",
  subtitle: "mhvp-label",
  table: "mhvp-table",
  badge: "inline-flex items-center rounded-full border border-border bg-surface px-2 py-0.5 text-xs font-medium text-muted",
  badgeGold: "inline-flex items-center rounded-full bg-gold-soft px-2 py-0.5 text-xs font-medium text-fg",
  badgeSuccess: "inline-flex items-center rounded-full bg-success-bg px-2 py-0.5 text-xs font-medium text-success-fg",
  badgeWarning: "inline-flex items-center rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning-fg",
  badgeDanger: "inline-flex items-center rounded-full bg-danger-bg px-2 py-0.5 text-xs font-medium text-danger-fg",
} as const;
