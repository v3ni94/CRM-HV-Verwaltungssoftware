"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
type Plan = {
  id: string; text: string; gross: string; vat_percent: string; interval_months: number; start_date: string;
  end_date: string | null; next_due: string; ended_at: string | null; order_reference: string | null;
};

/** M14-01: recurring invoice plans of a ledger. Generating creates an unreviewed draft only. */
export function RecurringPlansPanel({ ledgers }: { ledgers: Option[] }) {
  const t = useTranslations("RecurringPlans");
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [rows, setRows] = useState<Plan[] | null>(null);
  const [ending, setEnding] = useState<string | null>(null);
  const [end, setEnd] = useState({ ended_at: "", reason: "" });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!ledger) return;
    const res = await bff<Plan[]>(`/api/bff/accounting/recurring-invoices?ledger_id=${ledger}`);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, [ledger]);
  useEffect(() => {
    void load();
  }, [load]);

  const act = async (path: string, init: RequestInit, done: string) => {
    setError(null);
    setMessage(null);
    const res = await bff<unknown>(`/api/bff/accounting/recurring-invoices/${path}`, init);
    if (!res.ok) return setError(res.message);
    setMessage(done);
    setEnding(null);
    await load();
  };

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      <label className="flex max-w-sm flex-col gap-1">
        <span className={ui.label}>{t("ledger")}</span>
        <select className={ui.input} value={ledger} onChange={(e) => setLedger(e.target.value)}>
          {ledgers.map((l) => (
            <option key={l.id} value={l.id}>{l.label}</option>
          ))}
        </select>
      </label>
      {error ? <p className={ui.alert} role="alert">{error}</p> : null}
      {message ? <p className={ui.success} role="status">{message}</p> : null}
      {rows === null ? null : rows.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("text")}</th>
                <th className="num">{t("gross")}</th>
                <th>{t("interval")}</th>
                <th>{t("nextDue")}</th>
                <th>{t("status")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.text}
                    {p.order_reference ? <span className={ui.small}> ({p.order_reference})</span> : null}
                  </td>
                  <td className="num">{formatEur(p.gross)}</td>
                  <td>{t("months", { count: p.interval_months })}</td>
                  <td>{formatDate(p.next_due)}</td>
                  <td>{p.ended_at ? t("ended", { date: formatDate(p.ended_at) }) : t("active")}</td>
                  <td className="flex flex-wrap gap-2">
                    {p.ended_at ? null : (
                      <>
                        <button type="button" className={ui.buttonSm} onClick={() => void act(`${p.id}/generate`, { method: "POST" }, t("generated"))}>
                          {t("generate")}
                        </button>
                        <button type="button" className={ui.buttonSm} onClick={() => setEnding(p.id)}>{t("end")}</button>
                      </>
                    )}
                    <button type="button" className={ui.buttonSm} onClick={() => void act(p.id, { method: "DELETE" }, t("deleted"))}>{t("delete")}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {ending ? (
        <section className={ui.card} data-testid="plan-end">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("endDate")}</span>
            <input className={ui.input} type="date" value={end.ended_at} onChange={(e) => setEnd((v) => ({ ...v, ended_at: e.target.value }))} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("endReason")}</span>
            <input className={ui.input} value={end.reason} onChange={(e) => setEnd((v) => ({ ...v, reason: e.target.value }))} />
          </label>
          <button
            type="button"
            className={ui.primary}
            disabled={!end.ended_at || end.reason.trim().length < 3}
            onClick={() => void act(`${ending}/end`, { method: "POST", body: JSON.stringify({ ended_at: end.ended_at, reason: end.reason.trim() }) }, t("endedDone"))}
          >
            {t("endConfirm")}
          </button>
        </section>
      ) : null}
    </div>
  );
}
