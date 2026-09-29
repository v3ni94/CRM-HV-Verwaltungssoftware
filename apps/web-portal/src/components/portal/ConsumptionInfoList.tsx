"use client";

import { useTranslations } from "next-intl";

import type { ConsumptionComponent, ConsumptionInfoRow } from "@/components/portal/types";
import { ui } from "@/lib/ui";

export function formatQuantity(component: ConsumptionComponent | null | undefined, estimatedLabel: string, none: string): string {
  if (!component) return none;
  const number = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(component.value));
  const unit = component.unit_of_measure ? ` ${component.unit_of_measure}` : "";
  return `${number}${unit}${component.kind === "estimated" ? ` (${estimatedLabel})` : ""}`;
}

export function monthLabel(month: string): string {
  const [year, m] = month.split("-");
  return `${m}.${year}`;
}

/** Monatliche Verbrauchsinformation der eigenen Einheit (Regel H03): je Monat Heizung und
 *  Warmwasser mit Vormonat, Vorjahresmonat und Objektdurchschnitt. Nur Werte der Datengrundlage;
 *  geschätzte Werte sind gekennzeichnet, fehlende Werte werden nicht durch Null ersetzt. Unterhalb
 *  von `md` eine Karte je Monat, ab `md` die Tabelle. */
export function ConsumptionInfoList({ rows }: { rows: ConsumptionInfoRow[] }) {
  const t = useTranslations("ConsumptionInfo");
  const estimated = t("estimated");
  const none = t("none");
  const components: { key: "heating" | "hot_water"; label: string }[] = [
    { key: "heating", label: t("heating") },
    { key: "hot_water", label: t("hotWater") },
  ];
  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{t("note")}</p>
      {rows.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      {rows.map((row) => (
        <section key={row.id} className={`${ui.card} flex flex-col gap-3`} aria-labelledby={`ci-${row.id}`}>
          <h2 id={`ci-${row.id}`} className={ui.h2}>
            {t("monthTitle", { month: monthLabel(row.month) })}
          </h2>
          <ul className="flex flex-col gap-2 md:hidden" aria-label={`${t("tableCaption")} ${monthLabel(row.month)}`} data-testid="ci-cards">
            {components.map((c) => (
              <li key={c.key} className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <div className="flex items-start justify-between gap-3">
                  <span className="font-medium">{c.label}</span>
                  <span className="whitespace-nowrap">{formatQuantity(row.values[c.key], estimated, none)}</span>
                </div>
                <dl className="mt-1 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 text-xs text-muted">
                  <dt>{t("previousMonth")}</dt>
                  <dd className="text-right">{formatQuantity(row.values.previous_month?.[c.key], estimated, none)}</dd>
                  <dt>{t("previousYear")}</dt>
                  <dd className="text-right">{formatQuantity(row.values.previous_year_month?.[c.key], estimated, none)}</dd>
                  <dt>{t("average")}</dt>
                  <dd className="text-right">{formatQuantity(row.values.property_average?.[c.key], estimated, none)}</dd>
                </dl>
              </li>
            ))}
          </ul>
          <div className={`${ui.tableScroll} hidden md:block`}>
            <table className={`${ui.table} ${ui.tableStickyCol}`}>
              <caption className="sr-only">
                {t("tableCaption")} {monthLabel(row.month)}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{t("component")}</th>
                  <th scope="col" className="num">{t("month")}</th>
                  <th scope="col" className="num">{t("previousMonth")}</th>
                  <th scope="col" className="num">{t("previousYear")}</th>
                  <th scope="col" className="num">{t("average")}</th>
                </tr>
              </thead>
              <tbody>
                {components.map((c) => (
                  <tr key={c.key}>
                    <td>{c.label}</td>
                    <td className="num whitespace-nowrap">{formatQuantity(row.values[c.key], estimated, none)}</td>
                    <td className="num whitespace-nowrap">{formatQuantity(row.values.previous_month?.[c.key], estimated, none)}</td>
                    <td className="num whitespace-nowrap">{formatQuantity(row.values.previous_year_month?.[c.key], estimated, none)}</td>
                    <td className="num whitespace-nowrap">{formatQuantity(row.values.property_average?.[c.key], estimated, none)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {row.estimated.length > 0 ? <p className={ui.help}>{t("estimatedHint")}</p> : null}
        </section>
      ))}
    </div>
  );
}
