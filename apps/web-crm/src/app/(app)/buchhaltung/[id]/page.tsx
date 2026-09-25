import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { OpenItemsTable, type OpenItem } from "@/components/accounting/OpenItemsTable";
import { PageHeader } from "@/components/ui/PageHeader";
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
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung", label: t("title") }]}
        title={ledger.data.name}
        description={`${t("leading")}: ${t(`system.${ledger.data.leading_system}`)} · ${t("lockedUntil")}: ${
          formatDate(ledger.data.locked_until) || t("notLocked")
        }`}
      />
      {ledger.data.leading_system !== "mhvp" ? <p className={ui.notice}>{t("parallelNotice")}</p> : null}
      <Link href={`/buchhaltung/${id}/auswertungen`} className={ui.button}>
        {t("reports.link")}
      </Link>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("trialBalance", { date: formatDate(today) })}</h2>
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("account")}</th>
              <th className="num">{t("debit")}</th>
              <th className="num">{t("credit")}</th>
              <th className="num">{t("balance")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.account_id}>
                <td>
                  {r.number} {r.name}
                </td>
                <td className="num">{formatEur(r.debit)}</td>
                <td className="num">{formatEur(r.credit)}</td>
                <td className="num">{formatEur(r.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tr("openItems", { date: formatDate(today) })}</h2>
        <OpenItemsTable rows={(open.data ?? []) as OpenItem[]} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("journal")}</h2>
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("number")}</th>
              <th>{t("date")}</th>
              <th>{t("text")}</th>
              <th>{t("status")}</th>
            </tr>
          </thead>
          <tbody>
            {(journal.data ?? []).map((e) => (
              <tr key={e.id}>
                <td className="tabular-nums">{e.number ? `${e.fiscal_year}-${e.number}` : ""}</td>
                <td>{formatDate(e.booking_date)}</td>
                <td>
                  {e.text}
                  {e.reversed_by_id ? <span className="ml-2 text-xs text-muted">{t("reversed")}</span> : null}
                </td>
                <td>{t(`entryStatus.${e.status}`)}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      </section>
    </div>
  );
}
