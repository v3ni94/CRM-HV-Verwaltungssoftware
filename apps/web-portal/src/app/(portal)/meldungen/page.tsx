import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { NewTicket } from "@/components/portal/NewTicket";
import type { Ticket } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Meldungen (M21): eigene Schadensmeldungen mit Verlauf, neue Meldung mit Fotoanhang. */
export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/tickets");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as Ticket[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <NewTicket />
      {rows.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
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
