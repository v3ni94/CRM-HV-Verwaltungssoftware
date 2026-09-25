import { getTranslations } from "next-intl/server";

import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import type { AccountStatement } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Sums decimal strings without float (cents as integers). */
function sumRemaining(values: string[]): string {
  let cents = 0n;
  for (const value of values) {
    const match = /^(-?)(\d+)(?:\.(\d{0,2}))?/.exec(String(value).trim());
    if (!match) continue;
    const sign = match[1] === "-" ? -1n : 1n;
    cents += sign * (BigInt(match[2] ?? "0") * 100n + BigInt((match[3] ?? "").padEnd(2, "0")));
  }
  const sign = cents < 0n ? "-" : "";
  const abs = cents < 0n ? -cents : cents;
  return `${sign}${abs / 100n}.${(abs % 100n).toString().padStart(2, "0")}`;
}

export default async function AccountPage() {
  const t = await getTranslations("Account");
  const { data, response } = await serverGet<AccountStatement>("/api/v1/portal/account");
  redirectIfUnauthenticated(response);
  const items = data?.items ?? [];
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className="mt-3 text-sm text-muted">{t("intro")}</p>
      </div>
      {data?.note ? <p className={ui.notice}>{data.note}</p> : null}
      {items.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-bg shadow-card">
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">{t("colContract")}</th>
                <th scope="col">{t("colDue")}</th>
                <th scope="col" className="num">
                  {t("colAmount")}
                </th>
                <th scope="col" className="num">
                  {t("colRemaining")}
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <td className="font-medium text-fg">{item.contract_number}</td>
                  <td className="text-muted">{formatDate(item.due_date)}</td>
                  <td className="num text-muted">{formatEur(item.amount)}</td>
                  <td className="num font-medium text-fg">{formatEur(item.remaining)}</td>
                </tr>
              ))}
              <tr>
                <td colSpan={3} className="font-medium text-fg">
                  {t("sumLabel")}
                </td>
                <td className="num font-semibold text-fg">{formatEur(sumRemaining(items.map((i) => i.remaining)))}</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
