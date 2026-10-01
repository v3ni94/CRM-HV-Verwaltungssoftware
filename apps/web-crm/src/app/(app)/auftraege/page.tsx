import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type OrderRow = {
  id: string;
  description: string;
  status: string;
  ticket_id: string | null;
  ticket_number: number | null;
  scheduled_at: string | null;
};

const STATUSES = ["requested", "quoted", "approved", "scheduled", "in_progress", "done", "invoiced", "accepted", "rejected", "cancelled"];

/** Auftragsübersicht (M19-01): alle Arbeitsaufträge mit Filter nach Status, read only. */
export default async function WorkOrdersPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const t = await getTranslations("WorkOrders");
  const status = sp.status && STATUSES.includes(sp.status) ? sp.status : "";
  const query = new URLSearchParams({ page_size: "100" });
  if (status) query.set("status", status);
  const response = await serverFetch(`/api/v1/work-orders?${query.toString()}`);
  redirectIfUnauthenticated(response);
  if (!response.ok) return <p role="alert" className={ui.alert}>{t("listError")}</p>;
  const rows = (await response.json()) as OrderRow[];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader title={t("listTitle")} description={t("listDescription")} />
      <form method="get" className="flex flex-wrap items-center gap-2" aria-label={t("filterStatus")}>
        <label htmlFor="order-status" className="text-sm text-muted">{t("filterStatus")}</label>
        <select id="order-status" name="status" defaultValue={status} className={`${ui.input} w-auto`}>
          <option value="">{t("filterAll")}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{t(`orderStatus.${s}`)}</option>
          ))}
        </select>
        <button type="submit" className={ui.button}>{t("filterApply")}</button>
      </form>
      {rows.length === 0 ? (
        <EmptyState title={t("listEmpty")} />
      ) : (
        <div className={ui.tableCard}>
          <table className={ui.table} data-testid="work-orders">
            <thead>
              <tr>
                <th>{t("columns.description")}</th>
                <th>{t("columns.status")}</th>
                <th>{t("columns.ticket")}</th>
                <th>{t("columns.scheduled")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id}>
                  <td><Link href={`/auftraege/${o.id}`} className="font-medium hover:underline">{o.description}</Link></td>
                  <td><span className={ui.badge}>{t(`orderStatus.${o.status}`)}</span></td>
                  <td>{o.ticket_id ? <Link href={`/tickets/${o.ticket_id}`} className="hover:underline">#{o.ticket_number}</Link> : ""}</td>
                  <td className="tabular-nums text-muted">{o.scheduled_at ? formatDateTime(o.scheduled_at) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
