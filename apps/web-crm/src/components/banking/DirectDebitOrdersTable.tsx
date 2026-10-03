"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type DdOrder = {
  id: string;
  debtor_name: string;
  debtor_iban_suffix?: string | null;
  mandate_reference: string;
  sequence_type: string;
  amount: string;
  due_date: string;
  bank_status: string;
  bank_status_reason_code?: string | null;
  collected_amount?: string | null;
};

/** Einzelaufträge eines Lastschriftlaufs (GAL-303, D37, D38): je Schuldner Mandat, Betrag,
 *  Bankstatus, Rückgabecode und eingezogener Betrag. Nur Anzeige, bucht nichts. Rücklastschrift
 *  und Teileinzug werden hervorgehoben, damit der betroffene Schuldner erkennbar ist. */
export function DirectDebitOrdersTable({ runId }: { runId: string }) {
  const t = useTranslations("BankActions.ddOrders");
  const [rows, setRows] = useState<DdOrder[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (rows) return;
    setBusy(true);
    setError(null);
    const res = await bff<DdOrder[]>(
      `/api/bff/accounting/direct-debits/${runId}/orders`,
    );
    setBusy(false);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  };
  const statusLabel = (s: string) =>
    ["open", "accepted", "rejected", "collected", "returned"].includes(s)
      ? t(`status_${s}` as "status_open")
      : s;
  const partial = (r: DdOrder) =>
    r.bank_status === "collected" &&
    r.collected_amount != null &&
    Number(r.collected_amount) < Number(r.amount);

  return (
    <div data-testid="dd-orders">
      <button
        type="button"
        className={ui.buttonSm}
        onClick={() => void toggle()}
        aria-expanded={open}
      >
        {open ? t("hide") : t("show")}
      </button>
      {open ? (
        <div className="mt-1 overflow-x-auto text-xs">
          {busy ? <p className="text-muted">{t("loading")}</p> : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          {rows && rows.length === 0 ? (
            <p className="text-muted">{t("empty")}</p>
          ) : null}
          {rows && rows.length > 0 ? (
            <div className={ui.tableScroll}>
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("debtor")}</th>
                    <th>{t("mandate")}</th>
                    <th>{t("dueDate")}</th>
                    <th className="num">{t("amount")}</th>
                    <th>{t("status")}</th>
                    <th className="num">{t("collected")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} data-testid={`dd-order-${r.id}`}>
                      <td>
                        {r.debtor_name}
                        {r.debtor_iban_suffix ? (
                          <span className="ml-1 text-muted">
                            …{r.debtor_iban_suffix}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        {r.mandate_reference}
                        <span className="block text-muted">
                          {r.sequence_type}
                        </span>
                      </td>
                      <td>{formatDate(r.due_date)}</td>
                      <td className="num">{formatEur(r.amount)}</td>
                      <td>
                        {statusLabel(r.bank_status)}
                        {r.bank_status_reason_code ? (
                          <span className="block text-muted">
                            {t("returnCode", {
                              code: r.bank_status_reason_code,
                            })}
                          </span>
                        ) : null}
                        {r.bank_status === "returned" ? (
                          <span className="block text-danger-fg" role="note">
                            {t("returnedNote")}
                          </span>
                        ) : null}
                      </td>
                      <td className="num">
                        {r.collected_amount != null
                          ? formatEur(r.collected_amount)
                          : "-"}
                        {partial(r) ? (
                          <span className="block text-warning-fg" role="note">
                            {t("partialNote")}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
