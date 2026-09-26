import Link from "next/link";
import { useTranslations } from "next-intl";

import type { DmsObject } from "@/lib/objektakte-dms";
import { ui } from "@/lib/ui";

function percent(value: number): string {
  return `${new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(value)} %`;
}

/** One tile of the DMS page (M29 Stufe 4): status, open review cases, completeness, missing. */
export function DmsObjectTile({ object }: { object: DmsObject }) {
  const t = useTranslations("Dms");
  const c = object.completeness;
  const complete = c.missing === 0;
  return (
    <Link href={`/dms/${encodeURIComponent(object.number)}`} className={`${ui.cardLink} flex h-full flex-col gap-3`} data-testid="dms-tile">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="mhvp-label tabular-nums">{object.number}</p>
          <p className="truncate font-semibold">{object.name}</p>
        </div>
        <span className={ui.badge}>{object.takeover_status}</span>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-sm">
        <div>
          <dt className="text-xs text-muted">{t("tile.openCases")}</dt>
          <dd className="tabular-nums font-medium">{object.open_review_cases}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t("tile.completeness")}</dt>
          <dd className="tabular-nums font-medium">{percent(c.percent)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{t("tile.missing")}</dt>
          <dd className="tabular-nums font-medium">{c.missing}</dd>
        </div>
      </dl>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface" aria-hidden>
        <div className="h-full bg-gold" style={{ width: `${Math.min(100, Math.max(0, c.percent))}%` }} />
      </div>
      <div className="flex flex-wrap gap-2">
        {complete ? (
          <span className={ui.badgeSuccess}>{t("tile.complete")}</span>
        ) : (
          <span className={ui.badgeWarning}>{t("tile.present", { present: c.present, required: c.required })}</span>
        )}
        {object.property_id ? null : <span className={ui.badge}>{t("tile.noProperty")}</span>}
      </div>
    </Link>
  );
}
