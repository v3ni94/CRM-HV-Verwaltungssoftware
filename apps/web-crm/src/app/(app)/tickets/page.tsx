import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { TicketCreate } from "@/components/tickets/TicketForms";
import { TicketsList } from "@/components/tickets/TicketsList";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function TicketsPage({ searchParams }: { searchParams: Promise<{ merged?: string }> }) {
  const t = await getTranslations("Tickets");
  const api = serverApi();
  // M36: merged source tickets stay hidden unless the filter is switched on.
  const showMerged = (await searchParams).merged === "1";
  const { data, error, response } = await api.GET("/api/v1/tickets", {
    params: { query: { include_merged: showMerged } },
  });
  redirectIfUnauthenticated(response);
  const me = await api.GET("/api/v1/auth/me");
  const canApprove = me.data?.permissions.includes("tickets:approve") ?? false;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <TicketCreate />
      <div className="flex items-center gap-2 text-sm">
        <Link
          href={showMerged ? "/tickets" : "/tickets?merged=1"}
          role="checkbox"
          aria-checked={showMerged}
          className="inline-flex items-center gap-2 hover:underline"
          data-testid="toggle-merged"
        >
          <span aria-hidden="true" className="inline-block h-4 w-4 rounded border border-border text-center text-xs leading-4">
            {showMerged ? "✓" : ""}
          </span>
          {t("merge.showMerged")}
        </Link>
      </div>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <TicketsList
          initialTickets={data.map((tk) => ({
            id: String(tk.id),
            number: Number(tk.number),
            title: tk.title ? String(tk.title) : null,
            priority: String(tk.priority),
            status: String(tk.status),
            sla_due_at: tk.sla_due_at ? String(tk.sla_due_at) : null,
            sla_breached: Boolean(tk.sla_breached),
          }))}
          canApprove={canApprove}
        />
      )}
    </div>
  );
}
