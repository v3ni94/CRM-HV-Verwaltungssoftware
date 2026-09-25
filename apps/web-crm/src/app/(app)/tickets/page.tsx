import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { TicketCreate } from "@/components/tickets/TicketForms";
import { TicketTable, type TicketRow } from "@/components/tickets/TicketTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  new: "gold",
  in_progress: "warning",
  waiting: "neutral",
  done: "success",
  closed: "neutral",
  rejected: "danger",
};

const PRIORITY_VARIANT: Record<string, StatusPillVariant> = {
  low: "neutral",
  normal: "neutral",
  high: "warning",
  urgent: "danger",
  immediate: "danger",
};

export default async function TicketsPage() {
  const t = await getTranslations("Tickets");
  const { data, error, response } = await serverApi().GET("/api/v1/tickets");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <TicketCreate />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <>
          <ul className="flex flex-col gap-2 sm:hidden" data-testid="tickets-cards">
            {data.map((tk) => (
              <li key={String(tk.id)} className={ui.cardLink} data-testid="ticket-card">
                <Link href={`/tickets/${String(tk.id)}`} className="flex flex-col gap-1.5">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">
                      #{String(tk.number)} {String(tk.title ?? "")}
                    </span>
                  </span>
                  <span className="flex flex-wrap gap-1.5">
                    <StatusPill variant={PRIORITY_VARIANT[String(tk.priority)] ?? "neutral"} label={t(`priorities.${String(tk.priority)}`)} />
                    <StatusPill variant={STATUS_VARIANT[String(tk.status)] ?? "neutral"} label={t(`statuses.${String(tk.status)}`)} />
                  </span>
                  {tk.sla_due_at ? (
                    <span className="text-sm text-muted">
                      {formatDateTime(String(tk.sla_due_at))}
                      {tk.sla_breached ? <span className="ml-1 text-danger-fg">{t("breached")}</span> : null}
                    </span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
          <div className="hidden sm:block">
            <TicketTable rows={data as unknown as TicketRow[]} />
          </div>
        </>
      )}
    </div>
  );
}
