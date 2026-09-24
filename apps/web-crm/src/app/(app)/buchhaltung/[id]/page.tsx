import { getTranslations } from "next-intl/server";

import { OpenItemsTable, type OpenItem } from "@/components/accounting/OpenItemsTable";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type TrialRow = { account_id: string; number: string; name: string; debit: string; credit: string; balance: string };

export default async function LedgerPage({ params }: { params: Promise<{ id: string }> }) {
  const [t, tr, { id }] = await Promise.all([
    getTranslations("Accounting"),
    getTranslations("Receivables"),
    params,
  ]);
  const today = new Date().toISOString().slice(0, 10);
  const api = serverApi();
  const [ledger, journal, trial, open] = await Promise.all([
    api.GET("/api/v1/accounting/ledgers/{ledger_id}", { params: { path: { ledger_id: id } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/entries", { params: { path: { ledger_id: id }, query: { limit: 100 } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/trial-balance", { params: { path: { ledger_id: id }, query: { as_of: today } } }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/open-items", { params: { path: { ledger_id: id }, query: { as_of: today } } }),
  ]);
  redirectIfUnauthenticated(ledger.response);
  if (!ledger.data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(ledger.error as Problem | undefined, ledger.response.status)}
      </p>
    );
  }
  const rows = ((trial.data?.accounts ?? []) as TrialRow[]);
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className={ui.title}>{ledger.data.name}</h1>
        <p className="text-sm text-muted">
          {t("leading")}: {t(`system.${ledger.data.leading_system}`)} · {t("lockedUntil")}:{" "}
          {formatDate(ledger.data.locked_until) || t("notLocked")}
        </p>
      </div>
      {ledger.data.leading_system !== "mhvp" ? <p className={ui.notice}>{t("parallelNotice")}</p> : null}
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("trialBalance", { date: formatDate(today) })}</h2>
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("account")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("debit")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("credit")}</th>
              <th className="py-1.5 text-right font-medium">{t("balance")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.account_id} className="border-b border-border">
                <td className="py-1.5 pr-3">
                  {r.number} {r.name}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.debit)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.credit)}</td>
                <td className="py-1.5 text-right tabular-nums">{formatEur(r.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{tr("openItems", { date: formatDate(today) })}</h2>
        <OpenItemsTable rows={(open.data ?? []) as OpenItem[]} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("journal")}</h2>
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("number")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("date")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("text")}</th>
              <th className="py-1.5 font-medium">{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {(journal.data ?? []).map((e) => (
              <tr key={e.id} className="border-b border-border">
                <td className="py-1.5 pr-3 tabular-nums">{e.number ? `${e.fiscal_year}-${e.number}` : ""}</td>
                <td className="py-1.5 pr-3">{formatDate(e.booking_date)}</td>
                <td className="py-1.5 pr-3">
                  {e.text}
                  {e.reversed_by_id ? <span className="ml-2 text-xs text-muted">{t("reversed")}</span> : null}
                </td>
                <td className="py-1.5">{t(`entryStatus.${e.status}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
