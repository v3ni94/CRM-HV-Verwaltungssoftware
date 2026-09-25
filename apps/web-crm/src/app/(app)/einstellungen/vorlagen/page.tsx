import { getTranslations } from "next-intl/server";

import { TemplateSettings, type Template } from "@/components/tickets/TemplateSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Ticketvorlagen mit Checklisten und Pflicht-Zusatzfeldern (z. B. IBAN beim Kautionsticket). */
export default async function TemplatesPage() {
  const t = await getTranslations("TicketTemplates");
  const { data, error, response } = await serverApi().GET("/api/v1/ticket-templates");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-5">
      <PageHeader eyebrow={t("area")} title={t("title")} description={t("intro")} />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : (
        <TemplateSettings templates={data as unknown as Template[]} />
      )}
    </div>
  );
}
