"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Mietrechnung mit Umsatzsteuerausweis (M13-03 Folgepunkt, Regel M13-04): Liste, Erzeugen je
 * Zeitraum oder als Dauerrechnung, PDF (Entwurf mit Wasserzeichen hinter G1), Storno nur durch
 * Gutschrift. Beträge kommen fertig aus der API (Strings, kein Float). */
export type RentInvoiceOut = {
  id: string;
  number: string;
  kind: "invoice" | "standing" | "credit_note";
  status: "issued" | "cancelled";
  invoice_date: string;
  period_start: string;
  period_end: string;
  net_total: string;
  vat_total: string;
  gross_total: string;
  draft: boolean;
  document_id: string | null;
  cancels_invoice_id: string | null;
  cancelled_by_invoice_id: string | null;
  hinweis: string;
};

type Props = { contractId: string; vatOption: string; canUpdate: boolean };

function monthBounds(iso: string): { start: string; end: string } {
  const y = Number(iso.slice(0, 4));
  const m = Number(iso.slice(5, 7));
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  const mm = String(m).padStart(2, "0");
  return { start: `${y}-${mm}-01`, end: `${y}-${mm}-${String(last).padStart(2, "0")}` };
}

export function RentInvoicePanel({ contractId, vatOption, canUpdate }: Props) {
  const t = useTranslations("RentInvoices");
  const hasOption = vatOption === "commercial_full_vat" || vatOption === "commercial_reduced_vat";
  const [rows, setRows] = useState<RentInvoiceOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toISOString().slice(0, 7);
  const [month, setMonth] = useState(today);
  const [year, setYear] = useState(today.slice(0, 4));
  const [standing, setStanding] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<RentInvoiceOut[]>(`/api/bff/contracts/${contractId}/rent-invoices`);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, [contractId]);

  useEffect(() => {
    if (hasOption) void load();
  }, [hasOption, load]);

  if (!hasOption) return null;

  const create = async () => {
    setBusy(true);
    setError(null);
    const period = standing ? { start: `${year}-01-01`, end: `${year}-12-31` } : monthBounds(month);
    const res = await bff<RentInvoiceOut>(`/api/bff/contracts/${contractId}/rent-invoices`, {
      method: "POST",
      body: JSON.stringify({ period_start: period.start, period_end: period.end, standing }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  };

  const creditNote = async (invoiceId: string) => {
    if (!window.confirm(t("confirmCreditNote"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<RentInvoiceOut>(`/api/bff/contracts/${contractId}/rent-invoices/${invoiceId}/credit-note`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await load();
  };

  return (
    <section className={ui.card} data-testid="rent-invoices">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {canUpdate ? (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={standing} onChange={(e) => setStanding(e.target.checked)} />
            {t("standing")}
          </label>
          {standing ? (
            <label className={ui.label}>
              {t("year")}
              <input className={ui.input} type="number" min={2000} max={2200} value={year} onChange={(e) => setYear(e.target.value)} aria-label={t("year")} />
            </label>
          ) : (
            <label className={ui.label}>
              {t("month")}
              <input className={ui.input} type="month" value={month} onChange={(e) => setMonth(e.target.value)} aria-label={t("month")} />
            </label>
          )}
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void create()}>
            {standing ? t("createStanding") : t("create")}
          </button>
        </div>
      ) : null}
      {error ? <p className={`${ui.error} mt-2`}>{error}</p> : null}
      {rows === null ? (
        <p className={ui.help}>{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className={`${ui.help} mt-3`}>{t("none")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={`${ui.table} mt-3`}>
            <thead>
              <tr>
                <th>{t("number")}</th>
                <th>{t("kind")}</th>
                <th>{t("period")}</th>
                <th>{t("net")}</th>
                <th>{t("vat")}</th>
                <th>{t("gross")}</th>
                <th>{t("status")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className={ui.mono}>{r.number}</td>
                  <td>{t(`kinds.${r.kind}`)}</td>
                  <td>
                    {formatDate(r.period_start)} {t("to")} {formatDate(r.period_end)}
                  </td>
                  <td className={ui.num}>{formatEur(r.net_total)}</td>
                  <td className={ui.num}>{formatEur(r.vat_total)}</td>
                  <td className={ui.num}>{formatEur(r.gross_total)}</td>
                  <td>
                    <span className={r.status === "cancelled" ? ui.badgeWarning : r.draft ? ui.badge : ui.badgeSuccess}>
                      {r.status === "cancelled" ? t("cancelled") : r.draft ? t("draft") : t("issued")}
                    </span>
                  </td>
                  <td className="flex flex-wrap gap-2">
                    <a className={ui.buttonSm} href={`/api/bff/contracts/${contractId}/rent-invoices/${r.id}/pdf`} target="_blank" rel="noreferrer">
                      {t("pdf")}
                    </a>
                    {canUpdate && r.kind !== "credit_note" && r.status === "issued" ? (
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void creditNote(r.id)}>
                        {t("creditNote")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
