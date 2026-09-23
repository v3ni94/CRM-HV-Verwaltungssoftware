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
};
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
            }}
          />
        </label>
        <button type="button" className={ui.button} onClick={preview} disabled={busy || !month}>
          {t("preview")}
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
      {run ? (
        <>
          <p className="text-sm" data-testid="run-status">
            {t(`runStatus.${run.status}`)} ·{" "}
            {groups
              .map(([k, v]) => `${t(`itemStatus.${k}`)}: ${v.count} (${formatEur(v.amount)})`)
              .join(" · ")}
          </p>
          <table className="w-full border-collapse text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="py-1.5 pr-3 font-medium">{t("paymentType")}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t("amount")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("due")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
                <th className="py-1.5 font-medium">{t("message")}</th>
              </tr>
            </thead>
            <tbody>
              {run.items.map((i, n) => (
                <tr key={`${i.contract_id}-${i.payment_type_code}-${n}`} className="border-b border-border">
                  <td className="py-1.5 pr-3">{i.payment_type_code}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(i.amount)}</td>
                  <td className="py-1.5 pr-3">{formatDate(i.due_date)}</td>
                  <td className="py-1.5 pr-3">{t(`itemStatus.${i.status}`)}</td>
                  <td className="py-1.5 text-muted">{i.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}
    </section>
  );
}
