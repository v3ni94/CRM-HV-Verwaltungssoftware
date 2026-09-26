import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TicketThroughput } from "@/components/workspace/TicketThroughput";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Auswertung Tickets (operator 26.09.2026): throughput and effectiveness of inbound and
 *  outbound tickets and mails, GET /api/v1/workspace/ticket-analytics (tickets:read). */
export default async function TicketAnalyticsPage() {
  const t = await getTranslations("TicketThroughput");
  const { data: me, response } = await getMe();
  redirectIfUnauthenticated(response);
  if (!me?.permissions.includes("tickets:read")) notFound();
  return (
    <div className={ui.pageGap}>
      <PageHeader eyebrow={t("eyebrow")} title={t("title")} description={t("description")} />
      <TicketThroughput />
    </div>
  );
}
