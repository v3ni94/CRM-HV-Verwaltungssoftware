import { getTranslations } from "next-intl/server";

import { AuditExportPanel, type AuditExportRun } from "@/components/accounting/AuditExportPanel";
import { LiquidityReport, type LiquiditySnapshot } from "@/components/accounting/ReportsLiquidity";
import { PaymentsByDebtor, type PaymentsByDebtorRow } from "@/components/accounting/ReportsPaymentsByDebtor";
import { RevenueReport, type RevenueRow } from "@/components/accounting/ReportsRevenue";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { as_of?: string; start?: string; end?: string };

function firstOfYear(today: string): string {
  return `${today.slice(0, 4)}-01-01`;
}

export default async function LedgerReportsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Params>;
}) {
  const [{ id }, query, t] = await Promise.all([params, searchParams, getTranslations("Accounting")]);
  const today = new Date().toISOString().slice(0, 10);
  const asOf = query.as_of || today;
  const start = query.start || firstOfYear(today);
  const end = query.end || today;

  const api = serverApi();
  const ledger = await api.GET("/api/v1/accounting/ledgers/{ledger_id}", { params: { path: { ledger_id: id } } });
  redirectIfUnauthenticated(ledger.response);
  if (!ledger.data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(ledger.error as Problem | undefined, ledger.response.status)}
      </p>
    );
  }

  const [liquidity, paymentsByDebtor, revenue, auditExports] = await Promise.all([
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/liquidity", {
      params: { path: { ledger_id: id }, query: { as_of: asOf } },
    }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/payments-by-debtor", {
      params: { path: { ledger_id: id }, query: { start, end } },
    }),
    api.GET("/api/v1/accounting/ledgers/{ledger_id}/revenue", {
      params: { path: { ledger_id: id }, query: { start, end } },
    }),
    api.GET("/api/v1/accounting/audit-exports", { params: { query: { ledger_id: id } } }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { href: "/buchhaltung", label: t("title") },
          { href: `/buchhaltung/${id}`, label: ledger.data.name },
        ]}
        title={t("reports.title")}
        description={t("reports.description")}
      />
      <form className="grid gap-3 md:grid-cols-[auto_auto_auto_auto] md:items-end" role="search">
        <div>
          <label htmlFor="as_of" className={ui.label}>
            {t("reports.asOf")}
          </label>
          <input id="as_of" name="as_of" type="date" defaultValue={asOf} className={ui.input} />
        </div>
        <div>
          <label htmlFor="start" className={ui.label}>
            {t("reports.start")}
          </label>
          <input id="start" name="start" type="date" defaultValue={start} className={ui.input} />
        </div>
        <div>
          <label htmlFor="end" className={ui.label}>
            {t("reports.end")}
          </label>
          <input id="end" name="end" type="date" defaultValue={end} className={ui.input} />
        </div>
        <div>
          <button type="submit" className={ui.button}>
            {t("reports.filter")}
          </button>
        </div>
      </form>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("reports.liquidity.title")}</h2>
        {!liquidity.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(liquidity.error as Problem | undefined, liquidity.response.status)}
          </p>
        ) : (
          <LiquidityReport data={liquidity.data as unknown as LiquiditySnapshot} />
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>
          {t("reports.paymentsByDebtor.title", { start: formatDate(start), end: formatDate(end) })}
        </h2>
        {!paymentsByDebtor.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(paymentsByDebtor.error as Problem | undefined, paymentsByDebtor.response.status)}
          </p>
        ) : (
          <PaymentsByDebtor rows={paymentsByDebtor.data as unknown as PaymentsByDebtorRow[]} />
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("reports.revenue.title", { start: formatDate(start), end: formatDate(end) })}</h2>
        {!revenue.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(revenue.error as Problem | undefined, revenue.response.status)}
          </p>
        ) : (
          <RevenueReport rows={revenue.data as unknown as RevenueRow[]} />
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("reports.auditExport.title")}</h2>
        {!auditExports.data ? (
          <p role="alert" className={ui.alert}>
            {problemMessage(auditExports.error as Problem | undefined, auditExports.response.status)}
          </p>
        ) : (
          <AuditExportPanel
            ledgerId={id}
            runs={auditExports.data as unknown as AuditExportRun[]}
            defaultStart={start}
            defaultEnd={end}
          />
        )}
      </section>
    </div>
  );
}
