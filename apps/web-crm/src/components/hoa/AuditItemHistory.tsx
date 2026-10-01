"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type HistoryRow = { item_version: number; changes: Record<string, { old: unknown; new: unknown } | unknown>; occurred_at: string };

function show(value: unknown, empty: string): string {
  if (value === null || value === undefined || value === "") return empty;
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** Change history of one audit position (PÜ08, M25-05): every change with old and new value,
 *  loaded on demand. Notes and answers are never overwritten without a trace. */
export function AuditItemHistory({ itemId }: { itemId: string }) {
  const t = useTranslations("HoaWork");
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    const res = await bff<HistoryRow[]>(`/api/bff/hoa/audit-items/${itemId}/history`);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setError(null);
    setRows(res.data);
    setOpen(true);
  }

  return (
    <div className="flex flex-col gap-1">
      <button type="button" className={ui.buttonSm} onClick={() => void toggle()} data-testid={`history-toggle-${itemId}`}>
        {open ? t("audit.history.hide") : t("audit.history.show")}
      </button>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {open && rows ? (
        rows.length === 0 ? (
          <p className="text-xs text-muted">{t("audit.history.none")}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-xs" data-testid={`history-${itemId}`}>
            {rows.map((r) => (
              <li key={r.item_version}>
                <span className="text-muted">
                  V{r.item_version} · {formatDateTime(r.occurred_at)}
                </span>
                {Object.entries(r.changes).map(([field, change]) => {
                  const c = change as { old?: unknown; new?: unknown };
                  return (
                    <span key={field} className="block">
                      {field}: {show(c?.old, t("audit.history.empty"))} → {show(c?.new, t("audit.history.empty"))}
                    </span>
                  );
                })}
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
  );
}
