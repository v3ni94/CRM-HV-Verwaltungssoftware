import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { TicketCreate } from "@/components/tickets/TicketForms";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/tickets");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <TicketCreate />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1.5 pr-3 font-medium">{t("number")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("titleField")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("priority")}</th>
              <th className="py-1.5 pr-3 font-medium">{t("status")}</th>
              <th className="py-1.5 font-medium">{t("sla")}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((tk) => (
              <tr key={String(tk.id)} className="border-b border-border">
                <td className="py-1.5 pr-3 tabular-nums">{String(tk.number)}</td>
                <td className="py-1.5 pr-3">
                  <Link href={`/tickets/${String(tk.id)}`} className="font-medium hover:underline">
                    {String(tk.title ?? "")}
                  </Link>
                </td>
                <td className="py-1.5 pr-3">{t(`priorities.${String(tk.priority)}`)}</td>
                <td className="py-1.5 pr-3">{t(`statuses.${String(tk.status)}`)}</td>
                <td className="py-1.5">
                  {tk.sla_due_at ? formatDateTime(String(tk.sla_due_at)) : ""}
                  {tk.sla_breached ? <span className="ml-1 text-danger-fg">{t("breached")}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
