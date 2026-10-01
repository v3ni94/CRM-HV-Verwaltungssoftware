"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Row = {
  order_id: string;
  debtor_name: string;
  end_to_end_id: string;
  amount: string;
  bank_status: string;
  reason_code: string | null;
  reason: string | null;
  collected_amount: string | null;
  open_item_remaining: string;
  finding: string | null;
};
type Reconciliation = {
  status: string;
  control_sum: string;
  totals: Record<string, string>;
  open_findings: number;
  orders: Row[];
};
const STATUSES = ["accepted", "rejected", "collected", "returned"] as const;

/** M15-01: Bankrückmeldung je Lastschrift erfassen und mit dem offenen Posten abstimmen.
 * Erfasst nur die Rückmeldung; es wird nichts gebucht. Eine Rücklastschrift nach Ausgleich
 * erscheint als Befund und wird per Storno korrigiert. */
export function DirectDebitReconciliation({ runId }: { runId: string }) {
  const t = useTranslations("DirectDebitFeedback");
  const [data, setData] = useState<Reconciliation | null>(null);
  // Q02/M15-01: Auswahl mehrerer Lastschriften für die Sammelrückmeldung (ein Aufruf, alles oder nichts).
  const [selected, setSelected] = useState<string[]>([]);
  const [f, setF] = useState({ status: "collected", reason_code: "", reason: "", collected_amount: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Reconciliation>(`/api/bff/accounting/direct-debits/${runId}/reconciliation`);
    setBusy(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  const toggle = (id: string) => setSelected((cur) => (cur.includes(id) ? cur.filter((v) => v !== id) : [...cur, id]));
  const save = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { status: f.status, order_ids: selected };
    if (f.reason.trim()) body.reason = f.reason.trim();
    if (f.reason_code.trim()) body.reason_code = f.reason_code.trim();
    if (f.status === "collected" && selected.length === 1 && f.collected_amount.trim()) body.collected_amount = f.collected_amount.trim().replace(",", ".");
    const res = await bff<Reconciliation>(`/api/bff/accounting/direct-debits/${runId}/bank-status`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setData(res.data);
    setSelected([]);
  };

  return (
    <div className="flex flex-col gap-2">
      {data ? null : (
        <button type="button" className={ui.buttonSm} onClick={load} disabled={busy}>
          {t("show")}
        </button>
      )}
      {data ? (
        <section className="flex flex-col gap-2" data-testid="dd-reconciliation">
          <p className="text-sm">
            {t("summary", { sum: formatEur(data.control_sum), findings: data.open_findings })}
          </p>
          <p className="text-xs text-muted">
            {Object.entries(data.totals)
              .map(([k, v]) => `${t(`status.${k}`)}: ${formatEur(v)}`)
              .join(", ")}
          </p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      aria-label={t("selectAll")}
                      checked={data.orders.length > 0 && selected.length === data.orders.length}
                      onChange={(e) => setSelected(e.target.checked ? data.orders.map((o) => o.order_id) : [])}
                    />
                  </th>
                  <th>{t("debtor")}</th>
                  <th className="num">{t("amount")}</th>
                  <th>{t("bankStatus")}</th>
                  <th className="num">{t("collected")}</th>
                  <th className="num">{t("remaining")}</th>
                  <th>{t("finding")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.orders.map((r) => (
                  <tr key={r.order_id} className="align-top">
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t("selectOrder", { name: r.debtor_name })}
                        checked={selected.includes(r.order_id)}
                        onChange={() => toggle(r.order_id)}
                      />
                    </td>
                    <td>
                      {r.debtor_name}
                      <span className="block text-xs text-muted">{r.end_to_end_id}</span>
                    </td>
                    <td className="num">{formatEur(r.amount)}</td>
                    <td>
                      {t(`status.${r.bank_status}`)}
                      {r.reason_code || r.reason ? (
                        <span className="block text-xs text-muted">{[r.reason_code, r.reason].filter(Boolean).join(" ")}</span>
                      ) : null}
                    </td>
                    <td className="num">{r.collected_amount ? formatEur(r.collected_amount) : ""}</td>
                    <td className="num">{formatEur(r.open_item_remaining)}</td>
                    <td className={r.finding ? "text-warning-fg" : "text-muted"}>{r.finding ?? t("noFinding")}</td>
                    <td>
                      <button type="button" className={ui.buttonSm} onClick={() => setSelected(selected.length === 1 && selected[0] === r.order_id ? [] : [r.order_id])}>
                        {t("record")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected.length > 0 ? (
            <div className="flex flex-wrap items-end gap-2" data-testid="dd-feedback-form">
              <p className="w-full text-sm" data-testid="dd-selection">{t("selection", { count: selected.length })}</p>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("bankStatus")}</span>
                <select className={ui.input} value={f.status} onChange={(e) => setF((v) => ({ ...v, status: e.target.value }))}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{t(`status.${s}`)}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("reasonCode")}</span>
                <input className={`${ui.input} w-24`} maxLength={8} value={f.reason_code} onChange={(e) => setF((v) => ({ ...v, reason_code: e.target.value }))} />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("reason")}</span>
                <input className={ui.input} value={f.reason} onChange={(e) => setF((v) => ({ ...v, reason: e.target.value }))} />
              </label>
              {f.status === "collected" && selected.length === 1 ? (
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("collectedAmount")}</span>
                  <input className={`${ui.input} w-32`} inputMode="decimal" value={f.collected_amount} onChange={(e) => setF((v) => ({ ...v, collected_amount: e.target.value }))} />
                </label>
              ) : null}
              <button
                type="button"
                className={ui.button}
                disabled={busy}
                onClick={() => void save()}
              >
                {selected.length > 1 ? t("saveSelection", { count: selected.length }) : t("save")}
              </button>
            </div>
          ) : null}
          <p className={ui.help}>{t("hint")}</p>
        </section>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
