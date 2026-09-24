import { getTranslations } from "next-intl/server";

import { TicketEdit } from "@/components/tickets/TicketForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Comment = { body: string; internal: boolean; created_at: string };
type Event = { kind: string; at: string };

export default async function TicketPage({ params }: { params: Promise<{ ticketId: string }> }) {
  const { ticketId } = await params;
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/tickets/{ticket_id}", {
    params: { path: { ticket_id: ticketId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{problemMessage(error as Problem | undefined, response.status)}</p>;
  const comments = (data.comments ?? []) as Comment[];
  const events = (data.events ?? []) as Event[];
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>
        #{String(data.number)} {String(data.title ?? "")}
      </h1>
      {data.public_description ? <p className="text-sm">{String(data.public_description)}</p> : null}
      <TicketEdit id={ticketId} status={String(data.status)} priority={String(data.priority)} />
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("comments")}</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {comments.map((c, i) => (
            <li key={i} className={ui.card}>
              <div className="text-xs text-muted">
                {formatDateTime(c.created_at)} · {c.internal ? t("internal") : t("external")}
              </div>
              <div className="whitespace-pre-wrap">{c.body}</div>
            </li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className="font-medium">{t("history")}</h2>
        <ul className="text-xs text-muted">
          {events.map((e, i) => (
            <li key={i}>
              {formatDateTime(e.at)} · {e.kind}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
