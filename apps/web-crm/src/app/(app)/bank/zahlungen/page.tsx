import { getTranslations } from "next-intl/server";

import { OrderActions } from "@/components/banking/OrderActions";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function PaymentOrdersPage() {
  const t = await getTranslations("Payments");
  const { data, error, response } = await serverApi().GET("/api/v1/banking/payment-orders");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
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
              <th className="py-1.5 pr-3 font-medium">{t("execution")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("payee")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("purpose")}</th>
              <th className="py-1.5 pr-3 text-right font-medium">{t("amount")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
              <th className="py-1.5 font-medium">{t("actions")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((o) => (
              <tr key={o.id} className="border-b border-border align-top">
                <td className="py-1.5 pr-3">{formatDate(o.execution_date)}</td>
                <td className="py-1.5 pr-3">
                  {o.counterpart_name}
                  {o.counterpart_iban_suffix ? <span className="ml-1 text-xs text-muted">…{o.counterpart_iban_suffix}</span> : null}
                </td>
                <td className="py-1.5 pr-3">{o.purpose}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(String(o.amount))}</td>
                <td className="py-1.5 pr-3">
                  {t(`status_${o.status}`)}
                  {o.status === "draft" ? <span className="ml-1 text-xs text-muted">({t("approvals", { n: o.approvals ?? 0 })})</span> : null}
                </td>
                <td className="py-1.5">
                  <OrderActions id={o.id} status={o.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
