import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BoardEngagementDetail } from "@/components/portal/BoardEngagementDetail";
import type { BoardEngagementDetail as Detail } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Ein Prüfauftrag: Positionen, freigegebene Belege, Vermerke und Rückfragen (PÜ07, PÜ08).
 *  Die API prüft die Zugehörigkeit; ein fremder Prüfauftrag antwortet mit 404. */
export default async function AuditDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [t, { id }] = await Promise.all([getTranslations("Audit"), params]);
  const response = await serverFetch(`/api/v1/portal/board/engagements/${encodeURIComponent(id)}`);
  redirectIfUnauthenticated(response);
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error(`Prüfauftrag nicht ladbar (${response.status})`);
  const detail = (await response.json()) as Detail;
  return (
    <div className={ui.pageGap}>
      <Link href="/pruefung" className="text-sm text-muted underline">
        {t("back")}
      </Link>
      <BoardEngagementDetail detail={detail} />
    </div>
  );
}
