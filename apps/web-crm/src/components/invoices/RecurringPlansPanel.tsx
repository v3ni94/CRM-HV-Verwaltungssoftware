"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { RecurringPlanCreate } from "./RecurringPlanCreate";

type Option = { id: string; label: string };
type Plan = {
  id: string; text: string; gross: string; vat_percent: string; interval_months: number; start_date: string;
  end_date: string | null; next_due: string; ended_at: string | null; order_reference: string | null;
  anchor_day: number | null; service_contract_id: string | null;
};
const MONEY = /^\d+([.,]\d{1,2})?$/;

/** M14-01: recurring invoice plans of a ledger. Generating creates an unreviewed draft only. */
export function RecurringPlansPanel({ ledgers }: { ledgers: Option[] }) {
  const t = useTranslations("RecurringPlans");
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [rows, setRows] = useState<Plan[] | null>(null);
  const [ending, setEnding] = useState<string | null>(null);
  const [end, setEnd] = useState({ ended_at: "", reason: "" });
  const [editing, setEditing] = useState<string | null>(null);
  const [edit, setEdit] = useState({ text: "", gross: "", vat_percent: "", interval_months: "", end_date: "", order_reference: "", service_contract_id: "" });
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
    setEditing(null);
    await load();
  };
  const startEdit = (p: Plan) => {
    setEnding(null);
    setEditing(p.id);
    setEdit({
      text: p.text,
      gross: p.gross,
      vat_percent: p.vat_percent,
      interval_months: String(p.interval_months),
      end_date: p.end_date ?? "",
      order_reference: p.order_reference ?? "",
      service_contract_id: p.service_contract_id ?? "",
    });
  };
  const editValid =
    edit.text.trim().length > 0 && MONEY.test(edit.gross) && MONEY.test(edit.vat_percent) && /^\d{1,2}$/.test(edit.interval_months) && Number(edit.interval_months) > 0;
  const saveEdit = () =>
    act(
      editing ?? "",
      {
        method: "PATCH",
        body: JSON.stringify({
          text: edit.text.trim(),
          gross: edit.gross.replace(",", "."),
          vat_percent: edit.vat_percent.replace(",", "."),
          interval_months: Number(edit.interval_months),
          end_date: edit.end_date || null,
          order_reference: edit.order_reference.trim() || null,
          service_contract_id: edit.service_contract_id.trim() || null,
        }),
      },
      t("saved"),
    );

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
      <RecurringPlanCreate ledger={ledger} onCreated={load} />
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
                    {p.service_contract_id ? <span className={`${ui.small} block`}>{t("contractLinked")}</span> : null}
                    {p.anchor_day && p.anchor_day > 28 ? <span className={`${ui.small} block`}>{t("anchorDay", { day: p.anchor_day })}</span> : null}
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
                        <button type="button" className={ui.buttonSm} onClick={() => startEdit(p)}>{t("edit")}</button>
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
      {editing ? (
        <section className={ui.card} data-testid="plan-edit">
          <h2 className={ui.h2}>{t("editTitle")}</h2>
          <div className="grid gap-2 sm:grid-cols-3">
            {(["text", "gross", "vat_percent", "interval_months", "end_date", "order_reference", "service_contract_id"] as const).map((k) => (
              <label key={k} className="flex flex-col gap-1">
                <span className={ui.label}>{t(`editFields.${k}`)}</span>
                <input
                  className={ui.input}
                  type={k === "end_date" ? "date" : "text"}
                  value={edit[k]}
                  onChange={(e) => setEdit((v) => ({ ...v, [k]: e.target.value }))}
                />
              </label>
            ))}
          </div>
          <p className={ui.help}>{t("editHint")}</p>
          <div className="flex gap-2">
            <button type="button" className={ui.primary} disabled={!editValid} onClick={() => void saveEdit()}>{t("save")}</button>
            <button type="button" className={ui.button} onClick={() => setEditing(null)}>{t("cancel")}</button>
          </div>
        </section>
      ) : null}
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
