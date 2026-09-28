"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

export type TicketRef = { id: string; number: number; title: string | null; status?: string | null };

/** Folgevorgang (Regel M19-10): eine neue Mail zu einem länger abgeschlossenen Ticket legt ein
 *  Folgeticket an, statt das alte wieder zu öffnen. Das Folgeticket zeigt den Vorgänger, der
 *  Vorgänger seine Folgetickets; beide Hinweise verlinken auf das jeweils andere Ticket. */
export function TicketFollowUpLinks({ predecessor, successors }: { predecessor: TicketRef | null; successors: TicketRef[] }) {
  const t = useTranslations("Tickets.followUp");
  if (!predecessor && successors.length === 0) return null;
  const label = (ref: TicketRef) => `#${ref.number}${ref.title ? ` ${ref.title}` : ""}`;
  return (
    <div className="flex flex-col gap-1" data-testid="ticket-follow-up">
      {predecessor ? (
        <div role="status" className={ui.notice} data-testid="ticket-follow-up-of">
          {t("predecessor")}{" "}
          <Link href={`/tickets/${predecessor.id}`} className="font-medium text-fg hover:underline">
            {label(predecessor)}
          </Link>
          <div className="text-xs">{t("predecessorHint")}</div>
        </div>
      ) : null}
      {successors.length > 0 ? (
        <div role="status" className={ui.notice} data-testid="ticket-follow-ups">
          {t("successors", { count: successors.length })}{" "}
          {successors.map((s, i) => (
            <span key={s.id}>
              {i > 0 ? ", " : ""}
              <Link href={`/tickets/${s.id}`} className="font-medium text-fg hover:underline">
                {label(s)}
              </Link>
            </span>
          ))}
          <div className="text-xs">{t("successorsHint")}</div>
        </div>
      ) : null}
    </div>
  );
}
