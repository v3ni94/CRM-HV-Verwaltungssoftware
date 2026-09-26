import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { Suspense } from "react";

import { DigestCard, type Digest } from "@/components/dashboard/DigestCard";
import { TicketAnalytics } from "@/components/dashboard/TicketAnalytics";
import { PageHeader } from "@/components/ui/PageHeader";
import { TileSkeleton } from "@/components/ui/Skeleton";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
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

async function DashboardData() {
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
    <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-3" aria-label={t("tiles")}>
          {Object.entries(tiles).map(([key, value]) => {
            const href = TILE_LINKS[key];
            const body = (
              <>
                <span className="mhvp-label">{t(`tile.${key}`)}</span>
                <span className="mhvp-display mt-2 block font-semibold tabular-nums">{value.toLocaleString("de-DE")}</span>
                <span aria-hidden className="mt-3 block h-0.5 w-6 rounded-full bg-gold" />
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
                  <div className={ui.cardLift}>{body}</div>
                )}
              </li>
            );
          })}
        </ul>
        <p className={ui.notice}>{t("accountingLocked")}</p>
      </div>
      <aside className="flex w-full flex-col gap-3 lg:w-80 lg:shrink-0">
        <div className="flex items-baseline justify-between">
          <h2 className={ui.h2}>{t("upcoming")}</h2>
          <Link href="/kalender" className="text-sm text-muted transition duration-150 hover:text-fg hover:underline">
            {t("toCalendar")}
          </Link>
        </div>
        {upcoming.length === 0 ? (
          <p className={`${ui.card} text-sm text-muted`}>{t("noEntries")}</p>
        ) : (
          <ul className={`${ui.card} divide-y divide-border-soft p-0`}>
            {upcoming.map((u) => {
              const href = KIND_LINKS[u.kind];
              const row = (
                <>
                  <span className="w-16 shrink-0 tabular-nums text-xs text-muted">{formatDate(u.date)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{u.title}</span>
                    <span className={ui.badge}>{t(`kind.${u.kind}`)}</span>
                  </span>
                </>
              );
              return (
                <li key={`${u.kind}-${u.title}-${u.date}`} className="text-sm">
                  {href ? (
                    <Link href={href} className="flex items-center gap-3 px-4 py-3 transition duration-150 hover:bg-surface">
                      {row}
                    </Link>
                  ) : (
                    <div className="flex items-center gap-3 px-4 py-3">{row}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}

/** Karte "Tagesübersicht" (A40): dieselben Daten wie die Benachrichtigung um 07:00 Uhr. */
async function DigestData() {
  const t = await getTranslations("Digest");
  const response = await serverFetch("/api/v1/workspace/digest");
  redirectIfUnauthenticated(response);
  if (!response.ok) {
    return (
      <p role="alert" className={ui.alert}>
        {t("loadError")}
      </p>
    );
  }
  return <DigestCard digest={(await response.json()) as Digest} />;
}

export default async function DashboardPage() {
  const t = await getTranslations("Workspace");
  const { data: me } = await serverApi().GET("/api/v1/auth/me");
  const canSeeAnalytics = me?.permissions.includes("tickets:read") ?? false;
  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow={t("greetingLabel")} title={t("dashboard")} />
      <Suspense
        fallback={
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <TileSkeleton key={i} />
            ))}
          </div>
        }
      >
        <DashboardData />
      </Suspense>
      <Suspense fallback={<TileSkeleton />}>
        <DigestData />
      </Suspense>
      {canSeeAnalytics ? <TicketAnalytics /> : null}
    </div>
  );
}
