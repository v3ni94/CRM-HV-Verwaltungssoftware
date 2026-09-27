import { getTranslations } from "next-intl/server";

import type { WorkOrder } from "@/components/portal/types";
import { WorkOrderList } from "@/components/portal/WorkOrderList";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Aufträge (M22 Dienstleister): eigene Aufträge der Hausverwaltung. Status-Tabs und
 *  Textsuche sind client side in WorkOrderList. */
export default async function OrdersPage() {
  const t = await getTranslations("Orders");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/work-orders");
  await redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as WorkOrder[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <WorkOrderList orders={rows} />
    </div>
  );
}
