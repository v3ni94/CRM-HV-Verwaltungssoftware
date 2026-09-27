import { getTranslations } from "next-intl/server";

import { StartMetrics, type StartMetricsData } from "@/components/portal/StartMetrics";
import { StartTiles } from "@/components/portal/StartTiles";
import type { AccountStatement, Me, PortalDocument, Ticket, WorkOrder } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Meldungen mit diesen Statuswerten gelten als abgeschlossen (TICKET_STATUS in types.ts). */
const CLOSED_TICKET_STATUS = new Set(["done", "closed", "rejected"]);

/** Aufträge, die noch nicht begonnen wurden (ORDER_STATUS in types.ts vor in_progress). */
const OPEN_ORDER_STATUS = new Set(["draft", "requested", "quoted", "approved", "scheduled"]);

/** JSON eines parallel abgerufenen Endpunkts; jeder Fehler (Netz, Status, Parsing) wird zu null
 *  und lässt nur die betroffene Kennzahl weg, die Startseite bricht nie. */
async function settledJson<T>(settled: PromiseSettledResult<Response | null>): Promise<T | null> {
  if (settled.status !== "fulfilled" || settled.value === null || !settled.value.ok) return null;
  try {
    return (await settled.value.json()) as T;
  } catch {
    return null;
  }
}

function formatAmount(value: number): string {
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} EUR`;
}

const skip = Promise.resolve(null);

/** Start page after login: role aware. Providers see their orders only; tenants and owners
 *  see documents, tickets, account statement, meter reading and data change. Above the tiles
 *  a slim dashboard shows key figures per role (all endpoints fetched in parallel; a failing
 *  endpoint only hides its figure). */
export default async function StartPage() {
  const t = await getTranslations("Portal");
  const { data, error, response } = await serverApi().GET("/api/v1/portal/me");
  await redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const me = data as unknown as Me;
  const provider = me.roles.includes("provider");
  const board = me.roles.includes("board");
  const boardOnly = board && !me.roles.some((role) => role !== "board");
  const tenantOrOwner = !provider && !boardOnly;
  // Alle Kennzahlen-Abrufe parallel; nicht zur Rolle passende Endpunkte werden gar nicht erst
  // angefragt. 403 des Prüfungsraums (keine Beiratsrolle) bleibt still, wie jeder Fehler.
  const [noticesRes, ticketsRes, accountRes, documentsRes, ordersRes, boardRes] = await Promise.allSettled([
    provider ? skip : serverFetch("/api/v1/portal/notices"),
    tenantOrOwner ? serverFetch("/api/v1/portal/tickets") : skip,
    tenantOrOwner ? serverFetch("/api/v1/portal/account") : skip,
    tenantOrOwner ? serverFetch("/api/v1/portal/documents") : skip,
    provider ? serverFetch("/api/v1/portal/work-orders") : skip,
    board ? serverFetch("/api/v1/portal/board/engagements") : skip,
  ]);
  // Hint on new notices of the Schwarzes Brett (A54); any failure hides the hint only.
  const notices = await settledJson<{ is_new: boolean }[]>(noticesRes);
  const newNotices = (notices ?? []).filter((n) => n.is_new).length;
  const metrics: StartMetricsData = {};
  const tickets = await settledJson<Ticket[]>(ticketsRes);
  if (tickets) {
    metrics.openTickets = tickets.filter((row) => !CLOSED_TICKET_STATUS.has(row.status)).length;
    // A58: offene Terminvorschläge sind Teil der Ticket-Antwort, kein Zusatz-Endpunkt nötig.
    const proposals = tickets
      .flatMap((row) => row.appointment_proposals ?? [])
      .filter((p) => p.status === "proposed").length;
    if (proposals > 0) metrics.openProposals = proposals;
  }
  const account = await settledJson<AccountStatement>(accountRes);
  if (account) {
    const sum = account.items.reduce((total, item) => total + Number(item.remaining), 0);
    if (Number.isFinite(sum)) metrics.openBalance = formatAmount(sum);
  }
  const documents = await settledJson<PortalDocument[]>(documentsRes);
  if (documents) metrics.documents = documents.length;
  const orders = await settledJson<WorkOrder[]>(ordersRes);
  if (orders) {
    metrics.ordersOpen = orders.filter((row) => OPEN_ORDER_STATUS.has(row.status)).length;
    metrics.ordersInProgress = orders.filter((row) => row.status === "in_progress").length;
  }
  const engagements = await settledJson<unknown[]>(boardRes);
  if (engagements) metrics.boardEngagements = engagements.length;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("start.title")}</h1>
      <StartMetrics metrics={metrics} />
      <StartTiles me={me} newNotices={newNotices} />
    </div>
  );
}
