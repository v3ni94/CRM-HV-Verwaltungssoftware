import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Every tile opens the area it counts; tiles without an own screen stay plain. */
const TILE_LINKS: Record<string, string> = {
  properties: "/objekte",
  units: "/objekte",
  maintenance_due_30d: "/kalender",
  contacts: "/kontakte",
  active_contracts: "/vermietung",
  contracts_ending_90d: "/vermietung",
  open_ai_proposals: "/assistent",
  unread_notifications: "/kalender",
};
const KIND_LINKS: Record<string, string> = {
  appointment: "/kalender",
  maintenance: "/objekte",
  contract_end_date: "/vermietung",
  contract_termination_date: "/vermietung",
};

export default async function DashboardPage() {
  const t = await getTranslations("Workspace");
  const { data, error, response } = await serverApi().GET("/api/v1/workspace/dashboard");
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const tiles = data.tiles as Record<string, number>;
  const upcoming = data.upcoming as { kind: string; title: string; date: string }[];
  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className={ui.subtitle}>{t("greetingLabel")}</p>
        <h1 className={ui.title}>{t("dashboard")}</h1>
      </div>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4" aria-label={t("tiles")}>
        {Object.entries(tiles).map(([key, value]) => {
          const href = TILE_LINKS[key];
          const body = (
            <>
              <span className="mhvp-label">{t(`tile.${key}`)}</span>
              <span className="mt-2 block text-3xl font-semibold tabular-nums tracking-tight">{value.toLocaleString("de-DE")}</span>
              {href ? <span className="mt-2 block text-xs text-gold">{t("open")} →</span> : null}
            </>
          );
          return (
            <li key={key} data-testid={`tile-${key}`}>
              {href ? (
                <Link href={href} className={ui.cardLink}>
                  {body}
                </Link>
              ) : (
                <div className={ui.card}>{body}</div>
              )}
            </li>
          );
        })}
      </ul>
      <p className={ui.notice}>{t("accountingLocked")}</p>
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">{t("upcoming")}</h2>
          <Link href="/kalender" className="text-sm text-muted hover:text-fg hover:underline">
            {t("toCalendar")}
          </Link>
        </div>
        {upcoming.length === 0 ? (
          <p className="text-sm text-muted">{t("noEntries")}</p>
        ) : (
          <ul className={`${ui.card} divide-y divide-border p-0`}>
            {upcoming.map((u) => {
              const href = KIND_LINKS[u.kind];
              const row = (
                <>
                  <span className="w-24 shrink-0 tabular-nums text-muted">{formatDate(u.date)}</span>
                  <span className={ui.badge}>{t(`kind.${u.kind}`)}</span>
                  <span className="min-w-0 flex-1 truncate">{u.title}</span>
                </>
              );
              return (
                <li key={`${u.kind}-${u.title}-${u.date}`} className="text-sm">
                  {href ? (
                    <Link href={href} className="flex items-center gap-3 px-4 py-2.5 transition hover:bg-surface">
                      {row}
                    </Link>
                  ) : (
                    <div className="flex items-center gap-3 px-4 py-2.5">{row}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
