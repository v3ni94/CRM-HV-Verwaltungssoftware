"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type RunRow = {
  fee_setting_id: string;
  property_id: string;
  period_start: string;
  period_end: string;
  status: "preview" | "issued" | "already_issued" | "skipped" | "error";
  invoice_id: string | null;
  number: string | null;
  gross: string | null;
  detail: string | null;
};
type RunOut = { confirmed: boolean; period_date: string; invoice_date: string; issued: number; rows: RunRow[] };

/** Q02/Q15: Honorarlauf (POST /accounting/admin-fees-run). Erst Vorschau ohne Bestätigung, dann
 * Ausstellung nach ausdrücklicher Bestätigung; die Rechnungsnummern werden dabei fest vergeben.
 * Nichts wird versendet oder gebucht. */
export function AdminFeeRun({
  today,
  propertyLabel,
  onIssued,
}: {
  today: string;
  propertyLabel: (id: string) => string;
  onIssued?: () => void | Promise<void>;
}) {
  const t = useTranslations("AdminFees");
  const [periodDate, setPeriodDate] = useState(today);
  const [invoiceDate, setInvoiceDate] = useState(today);
  const [result, setResult] = useState<RunOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const call = async (confirm: boolean) => {
    setBusy(true);
    setError(null);
    const res = await bff<RunOut>("/api/bff/accounting/admin-fees-run", {
      method: "POST",
      body: JSON.stringify({ period_date: periodDate, invoice_date: invoiceDate, confirm }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setResult(res.data);
    if (confirm) await onIssued?.();
  };
  const issue = () => {
    if (!window.confirm(t("run.confirm", { count: dueCount }))) return;
    void call(true);
  };
  const dueCount = result && !result.confirmed ? result.rows.filter((r) => r.status === "preview").length : 0;

  return (
    <section className={ui.card} data-testid="fee-run">
      <h2 className="mb-2 text-sm font-semibold">{t("run.title")}</h2>
      <p className={ui.help}>{t("run.hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("run.periodDate")}</span>
          <input type="date" className={ui.input} value={periodDate} onChange={(e) => { setPeriodDate(e.target.value); setResult(null); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("run.invoiceDate")}</span>
          <input type="date" className={ui.input} value={invoiceDate} onChange={(e) => { setInvoiceDate(e.target.value); setResult(null); }} />
        </label>
        <button type="button" className={ui.button} onClick={() => void call(false)} disabled={busy || !periodDate || !invoiceDate}>
          {t("run.preview")}
        </button>
        {dueCount > 0 ? (
          <button type="button" className={ui.primary} onClick={issue} disabled={busy}>
            {t("run.issue", { count: dueCount })}
          </button>
        ) : null}
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {result ? (
        <div className="mt-2 flex flex-col gap-2">
          <p role="status" className="text-sm">
            {result.confirmed ? t("run.issuedCount", { count: result.issued }) : t("run.previewCount", { count: dueCount })}
          </p>
          <div className="overflow-x-auto">
            <table className="mhvp-table" data-testid="fee-run-rows">
              <thead>
                <tr>
                  <th>{t("property")}</th>
                  <th>{t("period")}</th>
                  <th className="num">{t("gross")}</th>
                  <th>{t("status")}</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={`${r.fee_setting_id}-${r.period_start}`}>
                    <td>{propertyLabel(r.property_id)}</td>
                    <td>{formatDate(r.period_start)} bis {formatDate(r.period_end)}</td>
                    <td className="num">{r.gross ? formatEur(r.gross) : ""}</td>
                    <td>
                      {t(`run.rowStatus.${r.status}`)}
                      {r.number ? ` (${r.number})` : ""}
                      {r.detail ? <span className="block text-xs text-muted">{r.detail}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
