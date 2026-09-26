import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/ui/PageHeader";
import { WorkOrderProposals, type WorkOrderProposalsData } from "@/components/workorders/WorkOrderProposals";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Arbeitsauftrag (A74): appointment proposals of the provider with status and the confirmed
 *  appointment; read only for the office (tickets:read). */
export default async function WorkOrderPage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  const t = await getTranslations("WorkOrders");
  const response = await serverFetch(`/api/v1/work-orders/${encodeURIComponent(orderId)}/appointment-proposals`);
  redirectIfUnauthenticated(response);
  if (!response.ok) return <p role="alert" className={ui.alert}>{t("notFound")}</p>;
  const data = (await response.json()) as WorkOrderProposalsData;
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        breadcrumb={[{ href: "/tickets", label: t("breadcrumbTickets") }]}
        title={t("title")}
        description={data.description}
      />
      <WorkOrderProposals initial={data} />
    </div>
  );
}
