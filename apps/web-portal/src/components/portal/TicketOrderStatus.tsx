"use client";

import { useTranslations } from "next-intl";

import { type TicketWorkOrder, formatDateTime } from "@/components/portal/types";
import { ui } from "@/lib/ui";

const KNOWN = ["requested", "quoted", "approved", "scheduled", "in_progress", "done", "invoiced", "accepted", "rejected", "cancelled"];

/** AM06 (GAJ-402, Abschnitt 14): laufender Auftragsstatus je Meldung für den Bewohner. Ohne
 *  Dienstleister, Preis oder interne Vermerke. */
export function TicketOrderStatus({ orders }: { orders: TicketWorkOrder[] }) {
  const t = useTranslations("Tickets");
  if (orders.length === 0) return null;
  return (
    <section className={ui.card} aria-labelledby="ticket-orders-title">
      <h2 id="ticket-orders-title" className={ui.label}>
        {t("ordersTitle")}
      </h2>
      <ul className="flex flex-col gap-1 text-sm">
        {orders.map((o, i) => (
          <li key={o.id} className="flex flex-wrap items-center gap-2">
            <span>{t("orderNumber", { n: i + 1 })}</span>
            <span className={ui.badge}>{KNOWN.includes(o.status) ? t(`orderStatus.${o.status}`) : o.status}</span>
            {o.scheduled_at ? <span className="text-muted">{t("orderScheduled", { date: formatDateTime(o.scheduled_at) })}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
