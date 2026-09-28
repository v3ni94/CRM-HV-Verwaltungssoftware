import type { ReactNode } from "react";

/** Reusable empty state block: icon, title, hint and an optional action. Used wherever a page
 *  would otherwise print a bare "no data" text line. */
export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-surface px-6 py-10 text-center">
      {icon ? (
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-subtle" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      <p className="text-sm font-medium text-fg">{title}</p>
      {hint ? <p className="max-w-sm text-sm text-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
