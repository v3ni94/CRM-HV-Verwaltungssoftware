import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TicketAnalytics } from "@/components/dashboard/TicketAnalytics";
import { TicketThroughput } from "@/components/workspace/TicketThroughput";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Auswertung Tickets (operator 26.09.2026): throughput and effectiveness of inbound and
 *  outbound tickets and mails, GET /api/v1/workspace/ticket-analytics. Tenant administrators
 *  only (operator 27.09.2026): admin marker is tickets:delete (rule M2-07, held by
 *  tenant_admin, administrator and the platform administrator after a tenant switch);
 *  platform administrators are always included. Everyone else gets 404. */
export default async function TicketAnalyticsPage() {
  const t = await getTranslations("TicketThroughput");
  const { data: me, response } = await getMe();
  redirectIfUnauthenticated(response);
  const isAdmin = (me?.permissions.includes("tickets:delete") ?? false) || Boolean(me?.is_platform_admin);
  if (!isAdmin) notFound();
  return (
    <div className={ui.pageGap}>
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />
      <TicketThroughput />
      {/* Ticket statistics and open tickets, moved here from the start page (operator 27.09.2026). */}
      <TicketAnalytics />
    </div>
  );
}
