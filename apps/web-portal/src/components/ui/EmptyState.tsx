import type { ReactNode } from "react";

/** Portal twin of the CRM `components/ui/EmptyState` (ADR 0013): title, hint on what to do or
 *  when content appears, optional action. Server safe (no "use client"). Replaces a bare
 *  "no data" text line. */
export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface px-6 py-10 text-center" data-testid="empty-state">
      <p className="text-sm font-medium text-fg">{title}</p>
      {hint ? <p className="max-w-sm text-sm text-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
