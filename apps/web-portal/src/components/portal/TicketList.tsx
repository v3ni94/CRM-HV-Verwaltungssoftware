"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { ListToolbar, matchesSearch } from "@/components/portal/ListToolbar";
import { TICKET_STATUS, type Ticket } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Meldungsliste mit Status-Tabs (nur vorhandene Statuswerte) und Textsuche über Titel und
 *  Nummer; die Daten lädt weiterhin die Server-Seite. */
export function TicketList({ tickets }: { tickets: Ticket[] }) {
  const t = useTranslations("Tickets");
  const tf = useTranslations("ListFilter");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  if (tickets.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  const statuses = TICKET_STATUS.filter((value) => tickets.some((row) => row.status === value)).map((value) => ({
    value,
    label: t(`status.${value}`),
  }));
  const rows = tickets.filter(
    (row) => (status === null || row.status === status) && matchesSearch(search, row.title, row.number),
  );
  return (
    <div className={ui.sectionGap}>
      <ListToolbar search={search} onSearchChange={setSearch} statuses={statuses} status={status} onStatusChange={setStatus} />
      {rows.length === 0 ? <p className={ui.notice}>{tf("noResults")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/meldungen/${row.id}`} className={`${ui.cardLink} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {t("number")} {row.number}: {row.title}
                </span>
                <span className={ui.badge}>{t(`status.${row.status}`)}</span>
              </span>
              {(row.appointment_proposals ?? []).some((p) => p.status === "proposed") ? (
                <span className={`${ui.badge} w-fit`}>{t("appointmentsOpen")}</span>
              ) : null}
              {row.comments.length > 0 ? (
                <span className="text-xs text-subtle">
                  {row.comments.length} {t("history")}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
