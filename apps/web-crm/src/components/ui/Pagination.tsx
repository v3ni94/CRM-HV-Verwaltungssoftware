import Link from "next/link";

import { ui } from "@/lib/ui";

// Generic page navigation, derived from TicketsPagination (H7) for reuse in /mail
// (Betreibermeldung 27.09.2026: real page navigation instead of "1, 2, 3 always shows page 1").
// Server and client safe when `control.kind === "link"` (links only, no state); with
// `control.kind === "button"` it calls back into client state instead of navigating.
export type PaginationControl =
  | { kind: "link"; buildHref: (page: number) => string }
  | { kind: "button"; onChange: (page: number) => void; disabled?: boolean };

export type PaginationLabels = {
  label: string;
  range: (from: number, to: number, total: number) => string;
  page: (page: number, pages: number) => string;
  prev: string;
  next: string;
};

export function Pagination({
  page,
  pageSize,
  total,
  shown,
  control,
  labels,
  testId,
}: {
  page: number;
  pageSize: number;
  total: number;
  shown: number;
  control: PaginationControl;
  labels: PaginationLabels;
  testId?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = total === 0 ? 0 : from + shown - 1;

  const renderControl = (target: number, rel: "prev" | "next", text: string) => {
    if (control.kind === "link") {
      return (
        <Link href={control.buildHref(target)} className={ui.button} rel={rel}>
          {text}
        </Link>
      );
    }
    return (
      <button
        type="button"
        className={ui.button}
        disabled={control.disabled}
        onClick={() => control.onChange(target)}
      >
        {text}
      </button>
    );
  };

  return (
    <nav className="flex items-center gap-3 text-sm" aria-label={labels.label} data-testid={testId}>
      <span className="text-muted">{labels.range(from, to, total)}</span>
      <span className="ml-auto">{labels.page(page, pages)}</span>
      {page > 1 ? renderControl(page - 1, "prev", labels.prev) : null}
      {page < pages ? renderControl(page + 1, "next", labels.next) : null}
    </nav>
  );
}
