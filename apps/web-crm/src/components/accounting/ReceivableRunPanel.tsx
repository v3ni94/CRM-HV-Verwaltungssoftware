"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Item = {
  contract_id: string;
  payment_type_code: string;
  amount: string;
  due_date: string | null;
  status: string;
  message: string | null;
  // 7.5 evidence and difference to an already posted item (M13-01, M13-02)
  contract_version?: number | null;
  basis_valid_from?: string | null;
  difference_amount?: string | null;
};
type RunSummary = { id: string; period_month: string; status: string; created_at: string };
export type Run = {
  id: string;
  period_month: string;
  status: string;
  totals: Record<string, { count: number; amount: string } | number>;
  items: Item[];
};

/** Receivable run (M13, 7.5): preview first, posting only after confirmation; a stale preview
 *  is rejected by the API (409). Postings stay non leading until G1 (ADR 0007). */
export function ReceivableRunPanel({ initialMonth }: { initialMonth: string }) {
  const t = useTranslations("Receivables");
  const [month, setMonth] = useState(initialMonth);
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[] | null>(null);

  const loadRuns = async () => {
    setError(null);
    const res = await bff<RunSummary[]>(`/api/bff/accounting/receivable-runs?period_month=${month}-01`);
    if (res.ok) setRuns(res.data ?? []);
    else setError(res.message);
  };
  const openRun = async (id: string) => {
    setError(null);
    const res = await bff<Run>(`/api/bff/accounting/receivable-runs/${id}`);
    if (res.ok) setRun(res.data);
    else setError(res.message);
  };

  const preview = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Run>("/api/bff/accounting/receivable-runs", {
      method: "POST",
      body: JSON.stringify({ period_month: `${month}-01` }),
    });
    setBusy(false);
    if (res.ok) setRun(res.data);
    else setError(res.message);
  };
  const post = async () => {
    if (!run || !window.confirm(t("confirmPost"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<Run>(`/api/bff/accounting/receivable-runs/${run.id}/post`, { method: "POST" });
    setBusy(false);
    if (res.ok) setRun(res.data);
    else setError(res.message);
  };
  const groups = Object.entries(run?.totals ?? {}).filter(
    (e): e is [string, { count: number; amount: string }] => typeof e[1] === "object",
  );
  const ready = groups.find(([k]) => k === "ready")?.[1];
  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("month")}</span>
          <input
            type="month"
            className={ui.input}
            value={month}
            onChange={(e) => {
              setMonth(e.target.value);
              setRun(null);
              setRuns(null);
            }}
          />
        </label>
        <button type="button" className={ui.button} onClick={preview} disabled={busy || !month}>
          {t("preview")}
        </button>
        <button type="button" className={ui.secondary} onClick={loadRuns} disabled={busy || !month}>
          {t("earlierRuns")}
        </button>
        {run && run.status !== "posted" && ready ? (
          <button type="button" className={ui.primary} onClick={post} disabled={busy}>
            {t("post", { count: ready.count, amount: formatEur(ready.amount) })}
          </button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {runs ? (
        runs.length === 0 ? (
          <p className="text-sm text-muted">{t("noRuns")}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm" data-testid="run-list">
            {runs.map((r) => (
              <li key={r.id} className="flex items-center gap-2">
                <span>
                  {formatDate(r.created_at)} · {t(`runStatus.${r.status}`)}
                </span>
                <button type="button" className={ui.buttonSm} onClick={() => openRun(r.id)}>
                  {t("open")}
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
      {run ? (
        <>
          <p className="text-sm" data-testid="run-status">
            {t(`runStatus.${run.status}`)} ·{" "}
            {groups
              .map(([k, v]) => `${t(`itemStatus.${k}`)}: ${v.count} (${formatEur(v.amount)})`)
              .join(" · ")}
          </p>
          {typeof run.totals.skipped_pending_approval === "number" && run.totals.skipped_pending_approval > 0 ? (
            <p className={ui.notice} data-testid="run-skipped">
              {t("skippedPending", { count: run.totals.skipped_pending_approval })}
            </p>
          ) : null}
          <div className="overflow-x-auto">
<table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("paymentType")}</th>
                <th className="num">{t("amount")}</th>
                <th>{t("due")}</th>
                <th>{t("status")}</th>
                <th>{t("message")}</th>
              </tr>
            </thead>
            <tbody>
              {run.items.map((i, n) => (
                <tr key={`${i.contract_id}-${i.payment_type_code}-${n}`}>
                  <td>{i.payment_type_code}</td>
                  <td className="num">{formatEur(i.amount)}</td>
                  <td>{formatDate(i.due_date)}</td>
                  <td>{t(`itemStatus.${i.status}`)}</td>
                  <td className="text-muted">
                    {i.message}
                    {i.difference_amount ? ` ${t("difference", { amount: formatEur(i.difference_amount) })}` : ""}
                    {i.basis_valid_from ? (
                      <span className="block text-xs">
                        {t("basis", { date: formatDate(i.basis_valid_from), version: i.contract_version ?? 1 })}
                      </span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
</div>
        </>
      ) : null}
    </section>
  );
}
