import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BoardEngagementDetail } from "@/components/portal/BoardEngagementDetail";
import type { BoardEngagementDetail as Detail, BoardReport } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { filterQuery } from "@/lib/audit-filter";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Ein Prüfauftrag: Positionen (serverseitig gefiltert nach Konto, Lieferant, Datum, Text; A77),
 *  freigegebene Belege, Vermerke und Rückfragen (PÜ07, PÜ08) sowie die Prüfberichte mit der
 *  Stellungnahme des Beirats (A76). Die API prüft die Zugehörigkeit; ein fremder Prüfauftrag
 *  antwortet mit 404. */
export default async function AuditDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [t, { id }, query] = await Promise.all([getTranslations("Audit"), params, searchParams]);
  const base = `/api/v1/portal/board/engagements/${encodeURIComponent(id)}`;
  const response = await serverFetch(`${base}${filterQuery(query)}`);
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (response.status === 422) {
    // Invalid filter (e.g. reversed date range): show the unfiltered engagement with a hint.
    const plain = await serverFetch(base);
    redirectIfUnauthenticated(plain);
    if (plain.status === 404) notFound();
    if (!plain.ok) throw new Error(`Prüfauftrag nicht ladbar (${plain.status})`);
    const detail = (await plain.json()) as Detail;
    const reports = await loadReports(base);
    return (
      <div className={ui.pageGap}>
        <Link href="/pruefung" className="text-sm text-muted underline">
          {t("back")}
        </Link>
        <p role="alert" className={ui.alert}>
          {t("filter.invalid")}
        </p>
        <BoardEngagementDetail detail={detail} reports={reports} />
      </div>
    );
  }
  if (!response.ok) throw new Error(`Prüfauftrag nicht ladbar (${response.status})`);
  const detail = (await response.json()) as Detail;
  const reports = await loadReports(base);
  return (
    <div className={ui.pageGap}>
      <Link href="/pruefung" className="text-sm text-muted underline">
        {t("back")}
      </Link>
      <BoardEngagementDetail detail={detail} reports={reports} />
    </div>
  );
}

async function loadReports(base: string): Promise<BoardReport[]> {
  const response = await serverFetch(`${base}/reports`);
  if (!response.ok) return [];
  return (await response.json()) as BoardReport[];
}
