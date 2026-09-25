import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { WorkOrderDetail } from "@/components/portal/WorkOrderDetail";
import type { WorkOrder } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const [t, { id }] = await Promise.all([getTranslations("Orders"), params]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/work-orders");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as WorkOrder[];
  const row = rows.find((r) => r.id === id);
  if (!row) notFound();
  return (
    <div className={ui.pageGap}>
      <Link href="/auftraege" className="text-sm text-muted underline">
        {t("back")}
      </Link>
      <WorkOrderDetail order={row} />
    </div>
  );
}
