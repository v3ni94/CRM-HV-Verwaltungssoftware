"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { ListToolbar, matchesSearch } from "@/components/portal/ListToolbar";
import { ORDER_STATUS, type WorkOrder } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Auftragsliste (M22) mit Status-Tabs (nur vorhandene Statuswerte) und Textsuche über die
 *  Beschreibung; die Daten lädt weiterhin die Server-Seite. */
export function WorkOrderList({ orders }: { orders: WorkOrder[] }) {
  const t = useTranslations("Orders");
  const tf = useTranslations("ListFilter");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  if (orders.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  const statuses = ORDER_STATUS.filter((value) => orders.some((row) => row.status === value)).map((value) => ({
    value,
    label: t(`status.${value}`),
  }));
  const rows = orders.filter(
    (row) => (status === null || row.status === status) && matchesSearch(search, row.description),
  );
  return (
    <div className={ui.sectionGap}>
      <ListToolbar search={search} onSearchChange={setSearch} statuses={statuses} status={status} onStatusChange={setStatus} />
      {rows.length === 0 ? <p className={ui.notice}>{tf("noResults")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/auftraege/${row.id}`} className={`${ui.cardLink} flex flex-wrap items-center justify-between gap-2`}>
              <span className="font-medium">{row.description}</span>
              <span className={ui.badge}>{t(`status.${row.status}`)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
