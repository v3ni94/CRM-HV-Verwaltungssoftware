"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { formatDateTime } from "@/lib/format";

type AuditEvent = {
  id: string;
  occurred_at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
};
type AuditPage = { items: AuditEvent[]; total: number; limit: number; offset: number };

const ACTIONS = [
  "tenant_domain_added",
  "tenant_domain_removed",
  "tenant_status_changed",
  "oidc_client_created",
  "oidc_client_secret_rotated",
  "oidc_client_activated",
  "oidc_client_deactivated",
  "maintenance_window_created",
  "maintenance_window_updated",
  "maintenance_window_cancelled",
  "availability_measurement_recorded",
] as const;
const PAGE_SIZE = 50;

/** AC02 (GA01-10/12): Plattformaudit, nur lesend (GET /platform/audit-events). */
export function PlatformAuditList() {
  const t = useTranslations("AC02");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const q = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (action) q.set("action", action);
    const res = await bff<AuditPage>(`/api/bff/platform/audit-events?${q.toString()}`);
    if (res.ok) {
      setPage(res.data);
      setError(null);
    } else setError(res.message);
  }, [action, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const total = page?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className={ui.pageGap}>
      {error ? <p className={ui.alert}>{error}</p> : null}
      <label className="flex items-center gap-2 text-sm">
        {t("filterAction")}
        <select
          className={`${ui.input} sm:w-auto`}
          value={action}
          onChange={(e) => {
            setOffset(0);
            setAction(e.target.value);
          }}
        >
          <option value="">{t("allActions")}</option>
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </label>
      {page && page.items.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {page && page.items.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("time")}</th>
                <th>{t("action")}</th>
                <th>{t("actor")}</th>
                <th>{t("target")}</th>
                <th>{t("payload")}</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((e) => (
                <tr key={e.id}>
                  <td>{formatDateTime(e.occurred_at)}</td>
                  <td>{e.action}</td>
                  <td>{e.actor_user_id ?? t("system")}</td>
                  <td>
                    {e.target_type} {e.target_id}
                  </td>
                  <td>
                    <details>
                      <summary>{t("show")}</summary>
                      <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(e.payload, null, 2)}</pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <div className="flex items-center gap-3 text-sm">
        <button type="button" className={ui.secondary} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          {t("prev")}
        </button>
        <span>{t("range", { from, to, total })}</span>
        <button type="button" className={ui.secondary} disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          {t("next")}
        </button>
      </div>
    </div>
  );
}
