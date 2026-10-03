import { getTranslations } from "next-intl/server";

import type { AccountStatement } from "@/components/portal/types";
import { EmptyState } from "@/components/ui/EmptyState";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format-date";
import { formatAmount } from "@/lib/format-eur";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Kontoauszug (M21): offene Posten der eigenen Verträge, Beträge in 1.234,56 EUR, Daten in
 *  TT.MM.JJJJ. */
export default async function AccountPage() {
  const t = await getTranslations("Account");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/account");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const statement = data as unknown as AccountStatement;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {statement.note ? <p className={ui.notice}>{statement.note}</p> : null}
      {statement.items.length === 0 ? (
        <EmptyState title={t("empty")} hint={t("emptyHint")} />
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">{t("contract")}</th>
                <th scope="col">{t("dueDate")}</th>
                <th scope="col" className="num">
                  {t("amount")}
                </th>
                <th scope="col" className="num">
                  {t("remaining")}
                </th>
              </tr>
            </thead>
            <tbody>
              {statement.items.map((item, i) => (
                <tr key={i}>
                  <td>{item.contract_number}</td>
                  <td className="whitespace-nowrap">
                    {formatDate(item.due_date)}
                  </td>
                  <td className="num whitespace-nowrap">{formatAmount(item.amount)} EUR</td>
                  <td className="num whitespace-nowrap">{formatAmount(item.remaining)} EUR</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
