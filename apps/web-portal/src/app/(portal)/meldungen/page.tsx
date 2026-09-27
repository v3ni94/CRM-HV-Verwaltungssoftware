import { getTranslations } from "next-intl/server";

import { NewTicket } from "@/components/portal/NewTicket";
import { TicketList } from "@/components/portal/TicketList";
import type { Ticket } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Meldungen (M21): eigene Schadensmeldungen mit Verlauf, neue Meldung mit Fotoanhang (A55),
 *  Hinweis auf offene Terminvorschläge des Handwerkers (A58). Status-Tabs und Textsuche
 *  sind client side in TicketList. */
export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/tickets");
  await redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as Ticket[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <NewTicket />
      <TicketList tickets={rows} />
    </div>
  );
}
