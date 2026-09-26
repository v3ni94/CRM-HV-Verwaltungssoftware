"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { TicketMailThread, type ThreadMessage } from "@/components/tickets/TicketMailThread";
import { TicketReplyPanel, type ReplyTarget } from "@/components/tickets/TicketReplyPanel";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Mailverlauf und Antwortformular des Tickets (operator 26.09.2026): der Verlauf wird über
 *  `GET /tickets/{id}/messages` geladen, "Auf diese Mail antworten" belegt das Formular mit
 *  dieser Mail vor, nach dem Einreichen wird der Verlauf neu geladen. */
export function TicketMailSection({ ticketId, canReply }: { ticketId: string; canReply: boolean }) {
  const t = useTranslations("Tickets.mailThread");
  const [messages, setMessages] = useState<ThreadMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<ReplyTarget | null>(null);

  const load = useCallback(async () => {
    const res = await bff<ThreadMessage[]>(`/api/bff/tickets/${ticketId}/messages`);
    if (res.ok) {
      setMessages(res.data);
      setError(null);
    } else {
      setMessages([]);
      setError(t("loadFailed"));
    }
  }, [ticketId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="ticket-mail-section">
      <section className="flex min-w-0 flex-col gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {messages === null ? null : (
          <TicketMailThread
            ticketId={ticketId}
            messages={messages}
            canReply={canReply}
            onReply={(m) => {
              setTarget({ messageId: m.id, at: m.direction === "in" ? m.received_at : m.sent_at });
              document.getElementById("ticket-reply")?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          />
        )}
      </section>
      <div id="ticket-reply">
        <TicketReplyPanel ticketId={ticketId} canSend={canReply} target={target} onSent={() => void load()} />
      </div>
    </div>
  );
}
