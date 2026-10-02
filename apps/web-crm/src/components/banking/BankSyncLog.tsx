"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type BankSyncRun = {
  id: string;
  source: string;
  status: string;
  counts: Record<string, number>;
  errors: string[];
  property_bank_account_id: string | null;
  document_id: string | null;
  connection_id?: string | null;
  created_at?: string | null;
};

/** GAB-03 (8.2): Sync-Protokoll je Lauf mit Zeitpunkt, Quelle, Status, Zählern (neu,
 *  Dubletten, automatisch gebucht, Vorschläge) und Fehlern aus GET /banking/runs. */
export function BankSyncLog({ limit = 20 }: { limit?: number }) {
  const t = useTranslations("BankSyncLog");
  const [runs, setRuns] = useState<BankSyncRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<BankSyncRun[]>(`/api/bff/banking/runs?limit=${limit}`).then((res) => {
      if (!res.ok) return setError(res.message);
      setRuns(res.data);
    });
  }, [limit]);

  const n = (r: BankSyncRun, key: string) => r.counts?.[key] ?? 0;
  return (
    <section className={ui.card} aria-labelledby="bank-sync-log">
      <h2 id="bank-sync-log" className="text-lg font-semibold">
        {t("title")}
      </h2>
      <p className={ui.help}>{t("help")}</p>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {!error && runs === null && <p className={ui.help}>{t("loading")}</p>}
      {runs !== null && runs.length === 0 && <p className={ui.help}>{t("empty")}</p>}
      {runs !== null && runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="bank-sync-log">
            <thead>
              <tr className="text-left">
                <th>{t("colTime")}</th>
                <th>{t("colSource")}</th>
                <th>{t("colStatus")}</th>
                <th className="text-right">{t("colNew")}</th>
                <th className="text-right">{t("colDuplicates")}</th>
                <th className="text-right">{t("colAuto")}</th>
                <th className="text-right">{t("colProposals")}</th>
                <th>{t("colErrors")}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-border align-top">
                  <td>{formatDateTime(r.created_at ?? null)}</td>
                  <td>{r.source}</td>
                  <td>{r.status}</td>
                  <td className="text-right">{n(r, "new")}</td>
                  <td className="text-right">{n(r, "duplicates") + n(r, "possible_duplicates")}</td>
                  <td className="text-right">{n(r, "auto_posted")}</td>
                  <td className="text-right">{n(r, "proposals")}</td>
                  <td>{r.errors.join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
