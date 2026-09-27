import { useTranslations } from "next-intl";
import Link from "next/link";

import { ATTENTION_BORDER, asAttention } from "@/components/tickets/attention";
import { AttentionBadge } from "@/components/tickets/TicketAttention";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /api/v1/tickets (subset used here); attention is derived on the server. */
export type MyTicket = {
  id: string;
  number: number;
  title: string | null;
  status: string;
  priority: string;
  sla_due_at: string | null;
  attention?: string;
  last_activity_at?: string | null;
};

/** Column "Meine Tickets" (operator 27.09.2026): tickets assigned to me in urgency order with
 *  the attention colour, at most ten, link to the full list. Pure presentation. */
export function MyTicketsColumn({ tickets, listHref, total }: { tickets: MyTicket[]; listHref: string; total?: number | null }) {
  const s = useTranslations("StartPage");
  const t = useTranslations("Tickets");
  return (
    <section className={ui.card} aria-labelledby="my-tickets-title" data-testid="my-tickets-column">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="my-tickets-title" className={ui.h2}>
          {s("tickets.title")}
        </h2>
        <Link href={listHref} className="text-sm text-muted transition duration-150 hover:text-fg hover:underline" data-testid="my-tickets-all">
          {s("tickets.all")}
        </Link>
      </div>
      <p className="mt-1 text-xs text-subtle">{s("tickets.description")}</p>
      {tickets.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{s("tickets.empty")}</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-1.5">
          {tickets.map((ticket) => {
            const attention = asAttention(ticket.attention);
            return (
              <li key={ticket.id} data-testid="my-ticket" data-attention={attention}>
                <Link
                  href={`/tickets/${ticket.id}`}
                  className={`block rounded-md bg-surface px-3 py-2 transition duration-150 hover:bg-surface-2 ${ATTENTION_BORDER[attention]}`}
                >
                  <span className="flex items-baseline gap-2">
                    <span className="shrink-0 tabular-nums text-xs text-muted">#{ticket.number}</span>
                    <span className="min-w-0 flex-1 truncate text-sm">{ticket.title ?? s("tickets.untitled")}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <AttentionBadge attention={attention} lastActivityAt={ticket.last_activity_at} />
                    {t.has(`statuses.${ticket.status}`) ? <span>{t(`statuses.${ticket.status}`)}</span> : null}
                    {ticket.sla_due_at ? <span>{s("tickets.due", { date: formatDate(ticket.sla_due_at) })}</span> : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {typeof total === "number" && total > tickets.length ? (
        <p className="mt-2 text-xs text-subtle">{s("tickets.more", { count: total - tickets.length })}</p>
      ) : null}
    </section>
  );
}
