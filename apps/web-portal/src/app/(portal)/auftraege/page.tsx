import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { WorkOrderActions } from "@/components/orders/WorkOrderActions";
import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { formatDateTime, formatEur } from "@/lib/format";
import { isProvider, orderStatusLabel, type PortalMe, type PortalWorkOrder } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function OrdersPage() {
  const t = await getTranslations("Orders");
  const [{ data: me, response }, { data: orders }] = await Promise.all([
    serverGet<PortalMe>("/api/v1/portal/me"),
    serverGet<PortalWorkOrder[]>("/api/v1/portal/work-orders"),
  ]);
  redirectIfUnauthenticated(response);
  if (me && !isProvider(me)) notFound();
  return (
    <div className="flex flex-col gap-5">
      <h1 className={ui.title}>{t("title")}</h1>
      {!orders || orders.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {orders.map((order) => (
            <li key={order.id} className={ui.card}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="max-w-2xl whitespace-pre-line text-sm text-fg">{order.description}</p>
                <span className={ui.badge}>
                  {t("statusLabel")}: {orderStatusLabel(order.status)}
                </span>
              </div>
              <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-1 text-sm">
                {order.quote_amount ? (
                  <div>
                    <dt className="mhvp-label">{t("quoteAmountLabel")}</dt>
                    <dd className="text-muted">{formatEur(order.quote_amount)}</dd>
                  </div>
                ) : null}
                {order.scheduled_at ? (
                  <div>
                    <dt className="mhvp-label">{t("scheduledLabel")}</dt>
                    <dd className="text-muted">{formatDateTime(order.scheduled_at)}</dd>
                  </div>
                ) : null}
              </dl>
              <WorkOrderActions orderId={order.id} status={order.status} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
