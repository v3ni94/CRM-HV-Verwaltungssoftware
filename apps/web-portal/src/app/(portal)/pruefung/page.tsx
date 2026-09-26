import { getFormatter, getTranslations } from "next-intl/server";
import Link from "next/link";

import type { BoardEngagement } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Prüfungsraum des Verwaltungsbeirats (7.9.2, A52): eigene Prüfaufträge. Nur lesend; Vermerke
 *  und Rückfragen werden im Detail erfasst. Ohne Beiratsrolle antwortet die API mit 403. */
export default async function AuditListPage() {
  const [t, format] = await Promise.all([getTranslations("Audit"), getFormatter()]);
  const response = await serverFetch("/api/v1/portal/board/engagements");
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as BoardEngagement[]) : [];
  const date = (value: string) => format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" });
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("roleNotice")}</p>
      {rows.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/pruefung/${row.id}`} className={`${ui.cardLink} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{row.legal_entity_name ?? row.legal_entity_id}</span>
                <span className={ui.badge}>{t(`sampling.${row.sampling}`)}</span>
              </span>
              <span className="text-sm text-muted">{row.purpose}</span>
              <span className="text-xs text-subtle">
                {t("period")} {date(row.period_from)} bis {date(row.period_to)}
                {row.open_questions ? ` · ${t("openQuestions", { count: row.open_questions })}` : ""}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
