"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import type { WorkOrderProposalsData } from "@/components/workorders/WorkOrderProposals";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type TicketWorkOrderRow = {
  id: string;
  description: string;
  status: string;
  scheduled_at: string | null;
};

type Summary = { open_count: number; scheduled_at: string | null };

/** Arbeitsaufträge des Tickets (A74): one row per order with a link to `/auftraege/{id}` and a
 *  short view of the provider's appointment proposals (open count, confirmed appointment).
 *  The proposals come from `GET /work-orders/{id}/appointment-proposals`; they are fetched in
 *  one batch for all orders and only once the section has scrolled into view, so a ticket
 *  with many orders costs nothing until the office looks at them. */
export function TicketWorkOrders({ orders }: { orders: TicketWorkOrderRow[] }) {
  const t = useTranslations("Tickets");
  const tOrders = useTranslations("WorkOrders");
  const sectionRef = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [summaries, setSummaries] = useState<Record<string, Summary> | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const node = sectionRef.current;
    if (!node || orders.length === 0) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [orders.length]);

  useEffect(() => {
    if (!visible || summaries) return;
    let cancelled = false;
    void Promise.all(
      orders.map((o) => bff<WorkOrderProposalsData>(`/api/bff/work-orders/${o.id}/appointment-proposals`)),
    ).then((results) => {
      if (cancelled) return;
      const next: Record<string, Summary> = {};
      let failed = false;
      orders.forEach((o, i) => {
        const res = results[i];
        if (res?.ok) next[o.id] = { open_count: res.data.open_count, scheduled_at: res.data.scheduled_at };
        else failed = true;
      });
      setSummaries(next);
      setError(failed);
    });
    return () => {
      cancelled = true;
    };
  }, [visible, summaries, orders]);

  return (
    <section ref={sectionRef} className="flex min-w-0 flex-col gap-2" data-testid="ticket-work-orders">
      <h2 className={ui.h2}>{t("workOrders.title")}</h2>
      {orders.length === 0 ? (
        <p className={ui.help}>{t("workOrders.empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {orders.map((o) => {
            const summary = summaries?.[o.id];
            const confirmedAt = summary ? summary.scheduled_at : o.scheduled_at;
            return (
              <li key={o.id} className={ui.card} data-testid="ticket-work-order">
                <div className="flex flex-wrap items-center gap-2">
                  <Link href={`/auftraege/${o.id}`} className="font-medium text-fg hover:underline">
                    {o.description}
                  </Link>
                  <span className={ui.badge}>{tOrders(`orderStatus.${o.status}`)}</span>
                  <Link href={`/auftraege/${o.id}`} className="ml-auto text-sm text-muted hover:underline">
                    {t("workOrders.detail")}
                  </Link>
                </div>
                <p className={ui.help} data-testid="ticket-work-order-proposals">
                  {summary
                    ? `${t("workOrders.open", { n: summary.open_count })}, ${
                        confirmedAt ? t("workOrders.confirmed", { when: formatDateTime(confirmedAt) }) : t("workOrders.noneConfirmed")
                      }`
                    : summaries && error
                      ? t("workOrders.loadError")
                      : confirmedAt
                        ? t("workOrders.confirmed", { when: formatDateTime(confirmedAt) })
                        : t("workOrders.loading")}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
