import { getFormatter, getTranslations } from "next-intl/server";

import type { AccountStatement } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

function formatAmount(value: string): string {
  return new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value));
}

/** Kontoauszug (M21): offene Posten der eigenen Verträge, Beträge in 1.234,56 EUR, Daten in
 *  TT.MM.JJJJ. */
export default async function AccountPage() {
  const [t, format] = await Promise.all([getTranslations("Account"), getFormatter()]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/account");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const statement = data as unknown as AccountStatement;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {statement.note ? <p className={ui.notice}>{statement.note}</p> : null}
      {statement.items.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("contract")}</th>
              <th>{t("dueDate")}</th>
              <th>{t("amount")}</th>
              <th>{t("remaining")}</th>
            </tr>
          </thead>
          <tbody>
            {statement.items.map((item, i) => (
              <tr key={i}>
                <td>{item.contract_number}</td>
                <td>{format.dateTime(new Date(item.due_date), { day: "2-digit", month: "2-digit", year: "numeric" })}</td>
                <td>{formatAmount(item.amount)} EUR</td>
                <td>{formatAmount(item.remaining)} EUR</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
