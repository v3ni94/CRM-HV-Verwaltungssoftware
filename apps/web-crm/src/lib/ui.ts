/** Shared Tailwind class sets on the neutral @mhvp/ui tokens (no CI values, V14). */
export const ui = {
  input:
    "w-full rounded border border-border bg-bg px-2 py-1.5 text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent",
  label: "block text-xs font-medium text-muted",
  button:
    "inline-flex items-center gap-1 rounded border border-border bg-surface px-3 py-1.5 text-sm text-fg hover:bg-bg focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50",
  primary:
    "inline-flex items-center gap-1 rounded bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 disabled:opacity-50",
  danger:
    "inline-flex items-center gap-1 rounded bg-danger-bg px-3 py-1.5 text-sm font-medium text-danger-fg hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50",
  error: "text-xs text-danger-fg",
  alert: "rounded border border-border bg-danger-bg px-3 py-2 text-sm text-danger-fg",
  notice: "rounded border border-border bg-surface px-3 py-2 text-sm",
  card: "rounded border border-border bg-surface p-4",
} as const;
