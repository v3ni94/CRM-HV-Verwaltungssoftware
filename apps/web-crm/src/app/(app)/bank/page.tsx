import { getTranslations } from "next-intl/server";

import { StatementImport } from "@/components/banking/StatementImport";
import { TransactionMatcher } from "@/components/banking/TransactionMatcher";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const OPEN = new Set(["new", "proposed", "needs_review"]);

export default async function BankPage() {
  const t = await getTranslations("Bank");
  const { data, error, response } = await serverApi().GET("/api/v1/banking/transactions", {
    params: { query: { limit: 200 } },
  });
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <StatementImport />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("date")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("counterpart")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("purpose")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("amount")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
              <th className="py-1.5 font-medium">{t("action")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((tx) => (
              <tr key={tx.id} className="border-b border-border align-top">
                <td className="py-1.5 pr-3">{formatDate(tx.booking_date)}</td>
                <td className="py-1.5 pr-3">
                  {tx.counterpart_name}
                  {tx.counterpart_iban_suffix ? (
                    <span className="ml-1 text-xs text-muted">…{tx.counterpart_iban_suffix}</span>
                  ) : null}
                </td>
                <td className="py-1.5 pr-3">{tx.purpose}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(tx.amount)}</td>
                <td className="py-1.5 pr-3">{t(`txStatus.${tx.status}`)}</td>
                <td className="py-1.5">
                  {OPEN.has(tx.status) && Number(tx.amount) > 0 && !tx.transfer_pair_id ? (
                    <TransactionMatcher txId={tx.id} amount={String(tx.amount)} />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
