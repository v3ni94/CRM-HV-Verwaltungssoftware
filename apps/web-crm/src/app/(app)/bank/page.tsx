import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { BankAccountOverview } from "@/components/banking/BankAccountOverview";
import { FinApiConnections } from "@/components/banking/FinApiConnections";
import { MatchingMetricsCard } from "@/components/banking/MatchingMetricsCard";
import { StatementImport } from "@/components/banking/StatementImport";
import { TransactionMatcher } from "@/components/banking/TransactionMatcher";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const OPEN = new Set(["new", "proposed", "needs_review"]);

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  new: "gold",
  needs_review: "warning",
  proposed: "warning",
  booked: "success",
  ignored: "neutral",
  split: "neutral",
};

export default async function BankPage() {
  const t = await getTranslations("Bank");
  const { data, error, response } = await serverApi().GET("/api/v1/banking/transactions", {
    params: { query: { limit: 200 } },
  });
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <nav aria-label={t("subpages")} className="flex flex-wrap gap-x-4 gap-y-1 text-sm font-medium">
        <Link href="/bank/zahlungen" className="hover:underline">
          {t("ordersLink")}
        </Link>
        <Link href="/bank/lastschriften" className="hover:underline">
          {t("directDebitsLink")}
        </Link>
      </nav>
      <BankAccountOverview />
      <FinApiConnections />
      <StatementImport />
      <MatchingMetricsCard />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("date")}</th>
              <th>{t("counterpart")}</th>
              <th>{t("purpose")}</th>
              <th className="num">{t("amount")}</th>
              <th>{t("status")}</th>
              <th>{t("action")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((tx) => (
              <tr key={tx.id} className="align-top">
                <td>{formatDate(tx.booking_date)}</td>
                <td>
                  {tx.counterpart_name}
                  {tx.counterpart_iban_suffix ? (
                    <span className="ml-1 text-xs text-muted">…{tx.counterpart_iban_suffix}</span>
                  ) : null}
                </td>
                <td>{tx.purpose}</td>
                <td className="num">{formatEur(tx.amount)}</td>
                <td>
                  <StatusPill variant={STATUS_VARIANT[tx.status] ?? "neutral"} label={t(`txStatus.${tx.status}`)} />
                </td>
                <td>
                  {OPEN.has(tx.status) && Number(tx.amount) > 0 && !tx.transfer_pair_id ? (
                    <TransactionMatcher txId={tx.id} amount={String(tx.amount)} />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
    </div>
  );
}
