"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Suggestion = {
  dispatch_id: string;
  date: string;
  channel: string;
  confirmed_delivery: boolean;
};
type Row = {
  contract_id: string;
  unit_number: string;
  deadline_orientation: string;
  delivered_at: string | null;
  access_suggestion: Suggestion | null;
  days_left: number;
  state:
    | "open"
    | "warning"
    | "expired"
    | "delivered_in_time"
    | "delivered_late";
};
type Overview = {
  policy: "block_claims" | "notice";
  notice: string;
  contracts: Row[];
};
type Settings = {
  policy: "block_claims" | "notice";
  watch_enabled: boolean;
  warn_days_first: number;
  warn_days_second: number;
};

const METHOD: Record<string, string> = {
  post: "post",
  email: "email",
  portal: "portal",
};

/** M17-04: deadline end per contract (orientation only, to be verified), access proposal from the
 *  dispatch (taken over by a person only) and the tenant switches for the behaviour after expiry. */
export function DeadlineOverviewPanel({
  id,
  canEdit,
}: {
  id: string;
  canEdit: boolean;
}) {
  const { busy, guard } = useBusy();
  const t = useTranslations("Billing.deadlineOverview");
  const tCommon = useTranslations("Common");
  const [data, setData] = useState<Overview | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [o, s] = await Promise.all([
      bff<Overview>(`/api/bff/statements/${id}/deadlines`),
      bff<Settings>("/api/bff/billing/deadline-settings"),
    ]);
    if (o.ok) setData(o.data);
    else setError(o.message);
    if (s.ok) setSettings(s.data);
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const adopt = async (row: Row) => {
    const s = row.access_suggestion;
    if (!s) return;
    setError(null);
    const res = await bff(
      `/api/bff/statements/${id}/results/${row.contract_id}/delivery`,
      {
        method: "PUT",
        body: JSON.stringify({
          delivery_method: METHOD[s.channel] ?? "post",
          delivered_at: s.date,
          evidence: t("evidenceText", { id: s.dispatch_id }),
        }),
      },
    );
    if (res.ok) await load();
    else setError(res.message);
  };

  const save = async (patch: Partial<Settings>) => {
    setError(null);
    const res = await bff<Settings>("/api/bff/billing/deadline-settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    if (res.ok) {
      setSettings(res.data);
      await load();
    } else setError(res.message);
  };

  if (!data)
    return error ? (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    ) : null;
  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{data.notice}</p>
      <div className={ui.tableScroll}>
      <table className={ui.table}>
        <thead>
          <tr>
            <th>{t("unit")}</th>
            <th>{t("deadline")}</th>
            <th>{t("access")}</th>
            <th>{t("state")}</th>
          </tr>
        </thead>
        <tbody>
          {data.contracts.length === 0 ? (
            <tr>
              <td colSpan={99} className="text-muted">
                {tCommon("emptyList")}
              </td>
            </tr>
          ) : null}
          {data.contracts.map((r) => (
            <tr key={r.contract_id}>
              <td>{r.unit_number}</td>
              <td>{formatDate(r.deadline_orientation)}</td>
              <td>
                {r.delivered_at ? (
                  formatDate(r.delivered_at)
                ) : r.access_suggestion ? (
                  <span className="flex flex-col gap-1">
                    {t("suggestion", {
                      date: formatDate(r.access_suggestion.date),
                      channel: r.access_suggestion.channel,
                    })}
                    {canEdit ? (
                      <button disabled={busy}
                        type="button"
                        className={ui.button}
                        onClick={guard(() => adopt(r))}
                      >
                        {t("adopt")}
                      </button>
                    ) : null}
                  </span>
                ) : (
                  t("none")
                )}
              </td>
              <td>
                <span
                  className={
                    r.state === "expired" ||
                    r.state === "delivered_late" ||
                    r.state === "warning"
                      ? ui.badgeWarning
                      : ui.badge
                  }
                >
                  {t(`states.${r.state}`, { days: r.days_left })}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {settings ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("policy")}</span>
            <select
              className={ui.input}
              value={settings.policy}
              disabled={!canEdit}
              onChange={(e) =>
                void save({ policy: e.target.value as Settings["policy"] })
              }
            >
              <option value="block_claims">{t("policyBlock")}</option>
              <option value="notice">{t("policyNotice")}</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={settings.watch_enabled}
              disabled={!canEdit}
              onChange={(e) => void save({ watch_enabled: e.target.checked })}
            />
            <span>
              {t("watch", {
                first: settings.warn_days_first,
                second: settings.warn_days_second,
              })}
            </span>
          </label>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
