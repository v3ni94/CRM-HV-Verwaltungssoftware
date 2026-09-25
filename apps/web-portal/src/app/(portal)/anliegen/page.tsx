import { getTranslations } from "next-intl/server";

import { TicketForm } from "@/components/tickets/TicketForm";
import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { ticketStatusLabel, type PortalMe, type PortalTicket } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const [{ data: me, response }, { data: tickets }] = await Promise.all([
    serverGet<PortalMe>("/api/v1/portal/me"),
    serverGet<PortalTicket[]>("/api/v1/portal/tickets"),
  ]);
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-6">
      <h1 className={ui.title}>{t("title")}</h1>
      <TicketForm contracts={me?.contracts ?? []} />
      {!tickets || tickets.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {tickets.map((ticket) => (
            <li key={ticket.id} className={ui.card}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="mhvp-label">{t("numberLabel", { number: ticket.number })}</p>
                  <h2 className={ui.h2}>{ticket.title}</h2>
                </div>
                <span className={ui.badge}>
                  {t("statusLabel")}: {ticketStatusLabel(ticket.status)}
                </span>
              </div>
              <div className="mt-3">
                <p className="mhvp-label">{t("historyLabel")}</p>
                {ticket.comments.length === 0 ? (
                  <p className="mt-1 text-sm text-subtle">{t("noComments")}</p>
                ) : (
                  <ul className="mt-1 flex flex-col gap-2">
                    {ticket.comments.map((comment, index) => (
                      <li key={index} className="rounded-md border-l-2 border-gold bg-surface px-3 py-2 text-sm text-muted">
                        {comment}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
