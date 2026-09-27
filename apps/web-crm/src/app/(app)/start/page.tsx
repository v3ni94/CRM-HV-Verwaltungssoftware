import { getTranslations } from "next-intl/server";

import { ApprovalsColumn, type ApprovalCounts } from "@/components/dashboard/ApprovalsColumn";
import { Greeting } from "@/components/dashboard/Greeting";
import { KpiStrip } from "@/components/dashboard/KpiStrip";
import { MyTicketsColumn, type MyTicket } from "@/components/dashboard/MyTicketsColumn";
import { TodayColumn, type TodayItem } from "@/components/dashboard/TodayColumn";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Days shown in the column "Heute" beyond today (operator 27.09.2026). */
const HORIZON_DAYS = 7;
const TICKET_LIMIT = 10;

/** Routes of generated calendar entries without an own href (see KIND_LINKS of the old page). */
const KIND_LINKS: Record<string, string> = {
  appointment: "/kalender",
  maintenance: "/objekte",
  contract_end_date: "/vermietung",
  contract_termination_date: "/vermietung",
};

type CalendarItem = {
  kind: string;
  title: string;
  date: string;
  entity_type?: string | null;
  entity_id?: string | null;
  href?: string | null;
  calendar_entry_id?: string | null;
  google_event_id?: string | null;
};
type Deadline = { id: string; kind: string; reference: string; due_on: string; href: string | null };

/** ISO date in the tenant time zone (Europe/Berlin), matching `services.local_today()`. */
function localIsoDate(offsetDays = 0): string {
  const now = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(now);
}

/** One fetch that never throws: a failed area shows its own notice, the others stay usable. */
async function load<T>(path: string): Promise<{ data: T | null; status: number }> {
  try {
    const response = await serverFetch(path);
    redirectIfUnauthenticated(response);
    if (!response.ok) return { data: null, status: response.status };
    return { data: (await response.json()) as T, status: response.status };
  } catch (error) {
    // redirect() throws on purpose (error.digest); everything else is a load error of this area.
    if (typeof error === "object" && error !== null && "digest" in error) throw error;
    return { data: null, status: 0 };
  }
}

/** Start page as personal workplace (operator 27.09.2026, design proposal 2): three columns
 *  Heute, Meine Tickets and Freigaben, the tenant wide numbers in a compact strip. All areas
 *  load server side in parallel; mobile stacks the columns. */
export default async function StartPage() {
  const t = await getTranslations("Workspace");
  const s = await getTranslations("StartPage");
  const { data: me, response: meResponse } = await getMe();
  redirectIfUnauthenticated(meResponse);
  const permissions = me?.permissions ?? [];
  const canReadTickets = permissions.includes("tickets:read");
  const userId = me?.user_id ?? null;
  const today = localIsoDate();
  const until = localIsoDate(HORIZON_DAYS);

  const ticketQuery = new URLSearchParams({ sort: "urgency", include_closed: "false", limit: String(TICKET_LIMIT) });
  if (userId) ticketQuery.set("assignee_user_id", userId);
  const [dashboard, calendar, deadlines, tickets, approvals] = await Promise.all([
    load<{ tiles: Record<string, number> }>("/api/v1/workspace/dashboard"),
    load<{ items: CalendarItem[] }>(`/api/v1/workspace/calendar?start=${today}&end=${until}`),
    load<Deadline[]>(`/api/v1/workspace/deadlines?status=open&from=${today}&to=${until}&limit=200`),
    canReadTickets && userId ? loadTickets(`/api/v1/tickets?${ticketQuery.toString()}`) : Promise.resolve({ data: null, status: 0, total: null }),
    load<ApprovalCounts>("/api/v1/workspace/approvals"),
  ]);

  const todayItems: TodayItem[] = [
    ...(calendar.data?.items ?? []).map<TodayItem>((item, index) => ({
      id: item.calendar_entry_id ?? item.google_event_id ?? `${item.kind}-${item.date}-${index}`,
      date: item.date,
      title: item.title,
      kind: item.kind,
      source: "calendar",
      href: item.href ?? KIND_LINKS[item.kind] ?? null,
    })),
    ...(deadlines.data ?? []).map<TodayItem>((row) => ({
      id: row.id,
      date: row.due_on,
      title: row.reference,
      kind: row.kind,
      source: "deadline",
      href: row.href ?? "/fristen",
    })),
  ].filter((item) => item.date >= today && item.date <= until);

  const failed = [calendar, deadlines].some((r) => r.data === null);
  const listHref = userId ? `/tickets?assignee_user_id=${userId}&sort=urgency` : "/tickets";
  return (
    <div className={ui.pageGap}>
      <div className="flex flex-col gap-3 border-b border-border-soft pb-5">
        <p className="mhvp-label">{s("eyebrow")}</p>
        <Greeting displayName={me?.display_name ?? null} email={me?.email ?? null} />
      </div>
      {dashboard.data ? (
        <KpiStrip tiles={dashboard.data.tiles} analyticsHref={canReadTickets ? "/auswertung/tickets" : null} />
      ) : (
        <p role="alert" className={ui.alert}>
          {s("loadError")}
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:items-start">
        <div className="flex flex-col gap-2">
          {failed ? (
            <p role="alert" className={ui.alert}>
              {s("loadError")}
            </p>
          ) : null}
          <TodayColumn items={todayItems} today={today} />
        </div>
        {canReadTickets ? (
          <div className="flex flex-col gap-2">
            {tickets.data === null ? (
              <p role="alert" className={ui.alert}>
                {s("loadError")}
              </p>
            ) : null}
            <MyTicketsColumn tickets={tickets.data ?? []} listHref={listHref} total={tickets.total} />
          </div>
        ) : null}
        <div className="flex flex-col gap-2">
          {approvals.data === null ? (
            <p role="alert" className={ui.alert}>
              {s("loadError")}
            </p>
          ) : null}
          <ApprovalsColumn counts={approvals.data ?? {}} />
        </div>
      </div>
      <p className={ui.notice}>{t("accountingLocked")}</p>
    </div>
  );
}

/** Ticket list with the total from the X-Total-Count header (link "und n weitere"). */
async function loadTickets(path: string): Promise<{ data: MyTicket[] | null; status: number; total: number | null }> {
  try {
    const response = await serverFetch(path);
    redirectIfUnauthenticated(response);
    if (!response.ok) return { data: null, status: response.status, total: null };
    const totalHeader = response.headers.get("x-total-count");
    const total = totalHeader ? Number.parseInt(totalHeader, 10) : null;
    return { data: (await response.json()) as MyTicket[], status: response.status, total: Number.isNaN(total) ? null : total };
  } catch (error) {
    if (typeof error === "object" && error !== null && "digest" in error) throw error;
    return { data: null, status: 0, total: null };
  }
}
