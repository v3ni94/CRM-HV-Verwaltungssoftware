import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ui } from "@/lib/ui";

export type TicketSummary = {
  id: string;
  number: number;
  title: string;
  status: string;
  priority: string;
};

/** Tickets section on a contact, property or unit page (operator 25.09.2026): open count and
 * links, independent from where the ticket was created (mail, portal, manual). */
export async function TicketsSection({ tickets }: { tickets: TicketSummary[] }) {
  const t = await getTranslations("Tickets");
  const open = tickets.filter((tk) => !["done", "closed", "rejected"].includes(tk.status));
  return (
    <section className={`${ui.card} flex flex-col gap-2`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("linkedTitle")}</h2>
        <span className={open.length > 0 ? ui.badgeWarning : ui.badge}>
          {t("openCount", { count: open.length })}
        </span>
      </div>
      {tickets.length === 0 ? (
        <p className="text-sm text-muted">{t("linkedEmpty")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {tickets.map((tk) => (
            <li key={tk.id} className="flex items-center justify-between gap-2 text-sm">
              <Link href={`/tickets/${tk.id}`} className="min-w-0 truncate hover:underline">
                #{tk.number} {tk.title}
              </Link>
              <span className={ui.badge}>{t(`statuses.${tk.status}`)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
