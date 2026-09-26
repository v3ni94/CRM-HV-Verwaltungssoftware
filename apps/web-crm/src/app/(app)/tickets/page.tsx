import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { TicketCreate } from "@/components/tickets/TicketForms";
import { TicketFilters } from "@/components/tickets/TicketFilters";
import { TicketsList } from "@/components/tickets/TicketsList";
import { TicketsPagination } from "@/components/tickets/TicketsPagination";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | undefined>;

// Filters this page forwards to GET /tickets unchanged (operator 25.09.2026, Tickets Suche und
// Filter): additive query params, see apps/api/src/mhvp/tickets/routers.py list_tickets.
const FORWARDED_KEYS = [
  "q",
  "assignee_user_id",
  "property_id",
  "unit_id",
  "contact_id",
  "contact_role",
  "status",
  "priority",
  "category",
  "team_id",
  "created_from",
  "created_to",
  "mine",
] as const;

// Page size of the list (review 26.09.2026, H7); GET /tickets reports the total in X-Total-Count.
const PAGE_SIZE = 50;

type Ticket = {
  id: string;
  number: number;
  title: string | null;
  priority: string;
  status: string;
  sla_due_at: string | null;
  sla_breached: boolean;
};

export default async function TicketsPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const t = await getTranslations("Tickets");
  const params = await searchParams;
  // M36: merged source tickets stay hidden unless the filter is switched on.
  const showMerged = params.merged === "1";

  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const query = new URLSearchParams();
  query.set("include_merged", String(showMerged));
  for (const key of FORWARDED_KEYS) {
    const value = params[key];
    if (value) query.set(key, value);
  }
  query.set("page", String(page));
  query.set("page_size", String(PAGE_SIZE));

  const response = await serverFetch(`/api/v1/tickets?${query.toString()}`);
  redirectIfUnauthenticated(response);
  const data = response.ok ? ((await response.json()) as Record<string, unknown>[]) : null;
  const total = Number.parseInt(response.headers.get("x-total-count") ?? "", 10);
  const totalCount = Number.isFinite(total) ? total : (data?.length ?? 0);

  function pageHref(target: number): string {
    const sp = new URLSearchParams();
    for (const key of FORWARDED_KEYS) {
      const value = params[key];
      if (value) sp.set(key, value);
    }
    if (showMerged) sp.set("merged", "1");
    if (target > 1) sp.set("page", String(target));
    const qs = sp.toString();
    return `/tickets${qs ? `?${qs}` : ""}`;
  }
  const error = response.ok ? null : ((await response.json().catch(() => null)) as Problem | null);

  const me = await getMe();
  const canApprove = me.data?.permissions.includes("tickets:approve") ?? false;
  const meUserId = me.data?.user_id ? String(me.data.user_id) : null;

  const mergedToggleQuery = new URLSearchParams();
  for (const key of FORWARDED_KEYS) {
    const value = params[key];
    if (value) mergedToggleQuery.set(key, value);
  }
  if (!showMerged) mergedToggleQuery.set("merged", "1");

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <TicketCreate />
      <TicketFilters meUserId={meUserId} />
      <div className="flex items-center gap-2 text-sm">
        <Link
          href={`/tickets${mergedToggleQuery.toString() ? `?${mergedToggleQuery.toString()}` : ""}`}
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
      ) : data.length === 0 && page === 1 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <>
          <TicketsList
            initialTickets={data.map(
              (tk): Ticket => ({
                id: String(tk.id),
                number: Number(tk.number),
                title: tk.title ? String(tk.title) : null,
                priority: String(tk.priority),
                status: String(tk.status),
                sla_due_at: tk.sla_due_at ? String(tk.sla_due_at) : null,
                sla_breached: Boolean(tk.sla_breached),
              }),
            )}
            canApprove={canApprove}
          />
          <TicketsPagination page={page} pageSize={PAGE_SIZE} total={totalCount} shown={data.length} buildHref={pageHref} />
        </>
      )}
    </div>
  );
}
