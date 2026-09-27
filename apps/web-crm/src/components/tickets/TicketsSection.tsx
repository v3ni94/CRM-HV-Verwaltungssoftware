"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ATTENTION_BORDER, asAttention } from "@/components/tickets/attention";
import { AttentionBadge, AttentionLegend } from "@/components/tickets/TicketAttention";
import { ui } from "@/lib/ui";

export type TicketSummary = {
  id: string;
  number: number;
  title: string;
  status: string;
  priority: string;
  // Traffic light (M19-09), derived on the server; optional for older callers.
  attention?: string;
  last_activity_at?: string | null;
};

const CLOSING = ["done", "closed", "rejected"];

/** Tickets section on a contact, property or unit page (operator 25.09.2026): open count and
 * links, independent from where the ticket was created (mail, portal, manual). Since
 * 26.09.2026 (M19-09) done, closed and rejected tickets are hidden until "Erledigte anzeigen"
 * is switched on; the rows carry the traffic light of the ticket list. */
export function TicketsSection({ tickets }: { tickets: TicketSummary[] }) {
  const t = useTranslations("Tickets");
  const [showClosed, setShowClosed] = useState(false);
  const open = tickets.filter((tk) => !CLOSING.includes(tk.status));
  const visible = showClosed ? tickets : open;
  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="tickets-section">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("linkedTitle")}</h2>
        <span className={open.length > 0 ? ui.badgeWarning : ui.badge}>
          {t("openCount", { count: open.length })}
        </span>
      </div>
      {tickets.length > open.length ? (
        <button
          type="button"
          role="checkbox"
          aria-checked={showClosed}
          className={`${ui.buttonSm} self-start`}
          onClick={() => setShowClosed((v) => !v)}
          data-testid="section-filter-closed"
        >
          {t("filters.showClosed")}
        </button>
      ) : null}
      {visible.length > 0 ? <AttentionLegend /> : null}
      {tickets.length === 0 ? (
        <p className="text-sm text-muted">{t("linkedEmpty")}</p>
      ) : visible.length === 0 ? (
        <p className="text-sm text-muted">{t("linkedAllClosed")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {visible.map((tk) => {
            const attention = asAttention(tk.attention);
            return (
              <li
                key={tk.id}
                className={`flex flex-wrap items-center justify-between gap-2 pl-2 text-sm ${ATTENTION_BORDER[attention]}`}
                data-testid="section-ticket"
                data-attention={attention}
              >
                <Link href={`/tickets/${tk.id}`} className="min-w-0 truncate hover:underline">
                  #{tk.number} {tk.title}
                </Link>
                <span className="flex items-center gap-2">
                  <AttentionBadge attention={attention} lastActivityAt={tk.last_activity_at} />
                  <span className={ui.badge}>{t(`statuses.${tk.status}`)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
