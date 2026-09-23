import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const TILE_LINKS: Record<string, string> = { contacts: "/kontakte", unread_notifications: "/kalender" };

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
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("dashboard")}</h1>
      <ul className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label={t("tiles")}>
        {Object.entries(tiles).map(([key, value]) => {
          const body = (
            <>
              <span className="block text-2xl font-semibold tabular-nums">{value.toLocaleString("de-DE")}</span>
              <span className="text-xs text-muted">{t(`tile.${key}`)}</span>
            </>
          );
          const href = TILE_LINKS[key];
          return (
            <li key={key} className={ui.card} data-testid={`tile-${key}`}>
              {href ? (
                <Link href={href} className="block hover:underline">
                  {body}
                </Link>
              ) : (
                body
              )}
            </li>
          );
        })}
      </ul>
      <p className={ui.notice}>{t("accountingLocked")}</p>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("upcoming")}</h2>
        {upcoming.length === 0 ? (
          <p className="text-sm text-muted">{t("noEntries")}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border rounded border border-border">
            {upcoming.map((u) => (
              <li key={`${u.kind}-${u.title}-${u.date}`} className="flex gap-3 px-3 py-2 text-sm">
                <span className="w-24 tabular-nums">{formatDate(u.date)}</span>
                <span className="w-28 text-xs text-muted">{t(`kind.${u.kind}`)}</span>
                <span>{u.title}</span>
              </li>
            ))}
          </ul>
        )}
        <Link href="/kalender" className="text-sm underline">
          {t("toCalendar")}
        </Link>
      </section>
    </div>
  );
}
