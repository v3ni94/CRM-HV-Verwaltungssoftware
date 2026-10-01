"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type DiffRow = {
  unit_number: string;
  component: string;
  period_month: string;
  posted_amount: string;
  new_amount: string;
  difference: string;
  kind: "claim" | "credit" | "none" | "manual";
};
type Draft = {
  id: string;
  component: string;
  period_month: string;
  difference: string;
  proposed_due: string | null;
  status: "draft" | "approved" | "rejected";
};
type Differences = { rows: DiffRow[]; total: string; mode: string; drafts: Draft[] };

const MODES = ["notice", "due_now", "next_instalment"] as const;

/** AE09 (W02, M12-L2): difference of months already posted after a plan change within the
 *  year. The variant is a tenant switch (default notice only). Drafts post nothing; the API
 *  demands G4 and a second person for the approval, the posting follows only with G1. */
export function PlanDifferences({ id }: { id: string }) {
  const t = useTranslations("HoaPlanChange");
  const [data, setData] = useState<Differences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setError(null);
    const res = await bff<Differences>(`/api/bff/hoa/plans/${id}/differences`);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  const run = async (path: string, method: "POST" | "PUT", body?: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/${path}`, {
      method,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else await load();
  };
  if (!data) {
    return (
      <div className="flex flex-col gap-2">
        <button type="button" className={ui.secondary} onClick={() => void load()} data-testid="plan-diff-load">
          {t("load")}
        </button>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="flex w-full flex-col gap-2" data-testid="plan-differences">
      <p className={ui.subtitle}>{t("title")}</p>
      <p className={ui.help}>{t("intro")}</p>
      <label className="flex items-center gap-2 text-sm">
        {t("mode")}
        <select
          value={data.mode}
          disabled={busy}
          data-testid="plan-diff-mode"
          onChange={(e) => void run("plan-change-settings", "PUT", { mode: e.target.value })}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {t(`modes.${m}`)}
            </option>
          ))}
        </select>
      </label>
      {data.rows.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("unit")}</th>
                <th>{t("component")}</th>
                <th>{t("month")}</th>
                <th className="num">{t("posted")}</th>
                <th className="num">{t("new")}</th>
                <th className="num">{t("difference")}</th>
                <th>{t("kindLabel")}</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={`${r.unit_number}-${r.component}-${r.period_month}`} data-testid={`plan-diff-row-${r.unit_number}-${r.period_month}`}>
                  <td>{r.unit_number}</td>
                  <td>{r.component}</td>
                  <td>{formatDate(r.period_month)}</td>
                  <td className="num">{formatEur(r.posted_amount)}</td>
                  <td className="num">{formatEur(r.new_amount)}</td>
                  <td className="num">{formatEur(r.difference)}</td>
                  <td>{t(`kind.${r.kind}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm" data-testid="plan-diff-total">
        {t("total", { amount: formatEur(data.total) })}
      </p>
      {data.mode === "notice" ? (
        <p className={ui.notice}>{t("noticeOnly")}</p>
      ) : (
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void run(`plans/${id}/differences/draft`, "POST")} data-testid="plan-diff-draft">
            {t("draft")}
          </button>
        </div>
      )}
      {data.drafts.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm" data-testid="plan-diff-drafts">
          {data.drafts.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2">
              <span>
                {formatDate(d.period_month)} {d.component}: {formatEur(d.difference)}
                {d.proposed_due ? ` (${t("due", { date: formatDate(d.proposed_due) })})` : ""}
              </span>
              <span className="text-muted">{t(`status.${d.status}`)}</span>
              {d.status === "draft" ? (
                <>
                  <button type="button" className={ui.secondary} disabled={busy} onClick={() => void run(`plan-differences/${d.id}/approve`, "POST")} data-testid={`plan-diff-approve-${d.id}`}>
                    {t("approve")}
                  </button>
                  <button type="button" className={ui.secondary} disabled={busy} onClick={() => void run(`plan-differences/${d.id}/reject`, "POST")}>
                    {t("reject")}
                  </button>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
