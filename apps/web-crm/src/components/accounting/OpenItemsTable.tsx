"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type OpenItem = {
  id: string;
  account_id?: string;
  account_number: string;
  kind: string;
  due_date: string | null;
  amount: string;
  remaining: string;
  /** Zugang der Zahlungsaufforderung beim Schuldner (M16-03), Grundlage des Verzugsmodus
   *  "30 Tage nach Fälligkeit und Zugang"; von einer Person erfasst, keine Automatik. */
  notice_received_on?: string | null;
};

/** Open items at a cut-off date (B02): remaining amount is computed from settlements. The
 *  date of notice receipt (`PATCH /accounting/open-items/{id}/notice-received`) is entered
 *  here per item; it is a fact recorded by a person, not derived automatically. */
export function OpenItemsTable({ rows: initialRows, canEdit = false }: { rows: OpenItem[]; canEdit?: boolean }) {
  const t = useTranslations("Receivables");
  const [rows, setRows] = useState(initialRows);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorId, setErrorId] = useState<string | null>(null);

  async function saveNotice(id: string, value: string) {
    setBusyId(id);
    setErrorId(null);
    const notice_received_on = value === "" ? null : value;
    const result = await bff<{ notice_received_on: string | null }>(`/api/bff/accounting/open-items/${id}/notice-received`, {
      method: "PATCH",
      body: JSON.stringify({ notice_received_on }),
    });
    setBusyId(null);
    if (result.ok) {
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, notice_received_on: result.data.notice_received_on } : r)));
    } else {
      setErrorId(id);
    }
  }

  if (rows.length === 0) return <p className="text-sm text-muted">{t("noOpenItems")}</p>;
  const total = rows.reduce((s, r) => s + Math.round(Number(r.remaining) * 100), 0) / 100;
  return (
    <div className="overflow-x-auto">
<table className="mhvp-table">
      <thead>
        <tr>
          <th>{t("account")}</th>
          <th>{t("due")}</th>
          <th className="num">{t("amount")}</th>
          <th className="num">{t("remaining")}</th>
          <th>{t("noticeReceivedOn")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} id={`open-item-${r.id}`}>
            <td>{r.account_number}</td>
            <td>{formatDate(r.due_date)}</td>
            <td className="num">{formatEur(r.amount)}</td>
            <td className="num">{formatEur(r.remaining)}</td>
            <td>
              {canEdit ? (
                <label className="flex flex-col gap-0.5">
                  <span className="sr-only">{t("noticeReceivedOn")}</span>
                  <input
                    type="date"
                    className={ui.input}
                    defaultValue={r.notice_received_on ?? ""}
                    disabled={busyId === r.id}
                    onBlur={(e) => {
                      if (e.target.value !== (r.notice_received_on ?? "")) void saveNotice(r.id, e.target.value);
                    }}
                    aria-label={`${t("noticeReceivedOn")}: ${r.account_number}`}
                  />
                </label>
              ) : (
                formatDate(r.notice_received_on ?? null)
              )}
              {errorId === r.id ? (
                <p role="alert" className={ui.error}>
                  {t("noticeReceivedOnError")}
                </p>
              ) : null}
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="font-medium">
          <td colSpan={3}>
            {t("total")}
          </td>
          <td className="num" data-testid="open-total">
            {formatEur(total.toFixed(2))}
          </td>
          <td />
        </tr>
      </tfoot>
    </table>
</div>
  );
}
