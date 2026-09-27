"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AuditRow = {
  id: string;
  event_id: string;
  entity_type: string;
  entity_id: string | null;
  changes: Record<string, unknown>;
  actor_user_id: string | null;
  occurred_at: string;
};

type FieldChange = { field: string; oldValue: string; newValue: string };

function cell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/** Flattens `{field: {old, new}}` into one row per field; plain values count as new. */
export function flattenChanges(changes: Record<string, unknown>): FieldChange[] {
  return Object.keys(changes)
    .sort()
    .map((field) => {
      const change = changes[field];
      if (change && typeof change === "object" && !Array.isArray(change) && ("old" in change || "new" in change)) {
        const c = change as { old?: unknown; new?: unknown };
        return { field, oldValue: cell(c.old), newValue: cell(c.new) };
      }
      return { field, oldValue: "", newValue: cell(change) };
    });
}

function query(entityType: string, entityId: string, page?: number, pageSize?: number): string {
  const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
  if (page) params.set("page", String(page));
  if (pageSize) params.set("page_size", String(pageSize));
  return params.toString();
}

/**
 * Ereignisprotokoll (Ergänzung 7.2): the change log of one record from GET /tenant/audit-log
 * with a CSV export. Needs `audit:read`; without it the panel shows a short hint instead of
 * an error.
 */
export function AuditLogPanel({ entityType, entityId, pageSize = 20 }: { entityType: string; entityId: string; pageSize?: number }) {
  const t = useTranslations("Audit");
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "forbidden" | "error">("loading");

  useEffect(() => {
    let active = true;
    void bff<AuditRow[]>(`/api/bff/tenant/audit-log?${query(entityType, entityId, page, pageSize)}`).then((result) => {
      if (!active) return;
      if (result.ok) {
        setRows((prev) => (page === 1 ? result.data : [...prev, ...result.data]));
        setMore(result.data.length === pageSize);
        setState("ready");
      } else {
        setState(result.status === 403 ? "forbidden" : "error");
      }
    });
    return () => {
      active = false;
    };
  }, [entityType, entityId, page, pageSize]);

  const exportHref = `/api/bff/tenant/audit-log/export?${query(entityType, entityId)}`;
  return (
    <section className="flex min-w-0 flex-col gap-2" data-testid="audit-log-panel" aria-labelledby="audit-log-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="audit-log-title" className={ui.h2}>
          {t("title")}
        </h2>
        {state === "ready" && rows.length > 0 ? (
          <a href={exportHref} download className={ui.buttonSm}>
            {t("export")}
          </a>
        ) : null}
      </div>
      {state === "loading" ? <p className={ui.help}>{t("loading")}</p> : null}
      {state === "forbidden" ? <p className={ui.help}>{t("noAccess")}</p> : null}
      {state === "error" ? (
        <p role="alert" className={ui.alert}>
          {t("error")}
        </p>
      ) : null}
      {state === "ready" && rows.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">{t("time")}</th>
                <th scope="col">{t("field")}</th>
                <th scope="col">{t("old")}</th>
                <th scope="col">{t("new")}</th>
                <th scope="col">{t("actor")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.flatMap((row) =>
                flattenChanges(row.changes).map((change) => (
                  <tr key={`${row.id}-${change.field}`}>
                    <td className="whitespace-nowrap">{formatDateTime(row.occurred_at)}</td>
                    <td className="font-medium">{change.field}</td>
                    <td className="max-w-xs break-words text-muted">{change.oldValue}</td>
                    <td className="max-w-xs break-words">{change.newValue}</td>
                    <td className="whitespace-nowrap text-xs text-muted">{row.actor_user_id ?? t("system")}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      ) : null}
      {state === "ready" && more ? (
        <button type="button" className={ui.buttonSm} onClick={() => setPage((p) => p + 1)}>
          {t("more")}
        </button>
      ) : null}
    </section>
  );
}
