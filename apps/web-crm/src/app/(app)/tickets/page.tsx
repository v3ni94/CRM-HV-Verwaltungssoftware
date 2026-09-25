import { getTranslations } from "next-intl/server";

import { TicketCreate } from "@/components/tickets/TicketForms";
import { TicketTable, type TicketRow } from "@/components/tickets/TicketTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/tickets");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <TicketCreate />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <TicketTable rows={data as unknown as TicketRow[]} />
      )}
    </div>
  );
}
