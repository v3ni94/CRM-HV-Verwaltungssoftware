import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { WorkOrder } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Aufträge (M22 Dienstleister): eigene Aufträge der Hausverwaltung. */
export default async function OrdersPage() {
  const t = await getTranslations("Orders");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/work-orders");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as WorkOrder[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {rows.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/auftraege/${row.id}`} className={`${ui.cardLink} flex flex-wrap items-center justify-between gap-2`}>
              <span className="font-medium">{row.description}</span>
              <span className={ui.badge}>{t(`status.${row.status}`)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
