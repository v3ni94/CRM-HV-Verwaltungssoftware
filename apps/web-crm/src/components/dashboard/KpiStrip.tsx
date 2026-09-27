import { useTranslations } from "next-intl";
import Link from "next/link";

import { ui } from "@/lib/ui";

/** Every tile opens the area it counts; tiles without an own screen stay plain. */
export const TILE_LINKS: Record<string, string> = {
  properties: "/objekte",
  units: "/objekte",
  maintenance_due_30d: "/kalender",
  contacts: "/kontakte",
  active_contracts: "/vermietung",
  contracts_ending_90d: "/vermietung",
  open_ai_proposals: "/assistent",
  unread_notifications: "/kalender",
};

/** Compact strip "Kennzahlen" of the start page (operator 27.09.2026, design proposal 2):
 *  tenant wide counts as small action chips, link to Auswertung Tickets. Pure presentation. */
export function KpiStrip({ tiles, analyticsHref }: { tiles: Record<string, number>; analyticsHref?: string | null }) {
  const t = useTranslations("Workspace");
  const s = useTranslations("StartPage");
  const entries = Object.entries(tiles);
  return (
    <section aria-labelledby="kpi-title" data-testid="kpi-strip" className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="kpi-title" className={ui.subtitle}>
          {t("tiles")}
        </h2>
        {analyticsHref ? (
          <Link href={analyticsHref} className="text-sm text-muted transition duration-150 hover:text-fg hover:underline">
            {s("toAnalytics")}
          </Link>
        ) : null}
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted">{s("kpiEmpty")}</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label={t("tiles")}>
          {entries.map(([key, value]) => {
            const href = TILE_LINKS[key];
            const body = (
              <>
                <span className="tabular-nums font-semibold text-fg">{value.toLocaleString("de-DE")}</span>
                <span className="text-muted">{t.has(`tile.${key}`) ? t(`tile.${key}`) : key}</span>
              </>
            );
            const cls = "inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs";
            return (
              <li key={key} data-testid={`tile-${key}`}>
                {href ? (
                  <Link href={href} className={`${cls} transition duration-150 hover:border-gold hover:text-fg`}>
                    {body}
                  </Link>
                ) : (
                  <span className={cls}>{body}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
