import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AppointmentProposals } from "@/components/portal/AppointmentProposals";
import { TicketComments } from "@/components/portal/TicketComments";
import type { Ticket } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Einzelne Meldung mit Verlauf und Kommentarfunktion. Es gibt keinen Einzel-Endpunkt; die
 *  Meldung wird aus der Liste der eigenen Meldungen entnommen (gleiche Zugriffsprüfung). */
export default async function TicketPage({ params }: { params: Promise<{ id: string }> }) {
  const [t, { id }] = await Promise.all([getTranslations("Tickets"), params]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/tickets");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as Ticket[];
  const row = rows.find((r) => r.id === id);
  if (!row) notFound();
  return (
    <div className={ui.pageGap}>
      <Link href="/meldungen" className="text-sm text-muted underline">
        {t("back")}
      </Link>
      <h1 className={ui.title}>
        {t("number")} {row.number}: {row.title}
      </h1>
      <span className={`${ui.badge} w-fit`}>{t(`status.${row.status}`)}</span>
      {(row.attachments ?? []).length > 0 ? (
        <p className="text-sm text-muted">
          {t("attachments")}: {row.attachments.map((a) => a.filename).join(", ")}
        </p>
      ) : null}
      <AppointmentProposals proposals={row.appointment_proposals ?? []} />
      <TicketComments ticketId={row.id} comments={row.comments} />
    </div>
  );
}
