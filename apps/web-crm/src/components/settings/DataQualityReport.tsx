"use client";
/** Datenqualität (entry standards ES-01 to ES-11): records deviating from the standard, grouped
 *  by section, each with a link to the record. Read only; nothing is corrected automatically. */
import Link from "next/link";
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DataQualityFinding = { rule: string; field: string | null; severity: "error" | "warning" | "hint"; message: string };
export type DataQualityItem = { entity_type: "property" | "contact" | "ticket"; entity_id: string; label: string; findings: DataQualityFinding[] };
export type DataQualitySection = { key: "properties" | "contacts" | "contact_emails" | "deadlines"; total: number; items: DataQualityItem[] };
export type DataQualityReportData = { generated_on: string; sections: DataQualitySection[]; sections_omitted: string[] };

const HREF: Record<DataQualityItem["entity_type"], string> = {
  property: "/objekte/",
  contact: "/kontakte/",
  ticket: "/tickets/",
};

export function DataQualityReport({ report }: { report: DataQualityReportData | null }) {
  const t = useTranslations("DataQuality");
  if (!report) {
    return (
      <p role="alert" className={ui.alert}>
        {t("loadError")}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted">
        {t("generatedOn", { date: formatDate(report.generated_on) })} · {t("handbook")}
      </p>
      {report.sections_omitted.length ? (
        <p className={ui.notice}>{t("omitted", { sections: report.sections_omitted.map((k) => t(`sections.${k}`)).join(", ") })}</p>
      ) : null}
      {report.sections.map((section) => (
        <section key={section.key} className={ui.card} data-testid={`dq-${section.key}`}>
          <h2 className="flex items-center justify-between gap-2 text-sm font-semibold">
            <span>{t(`sections.${section.key}`)}</span>
            <span className={section.total ? ui.badgeWarning : ui.badge}>{t("count", { shown: section.items.length, total: section.total })}</span>
          </h2>
          {section.items.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("empty")}</p>
          ) : (
            <ul className="mt-2 flex flex-col divide-y divide-border-soft">
              {section.items.map((item) => (
                <li key={item.entity_id} className="flex flex-wrap items-start justify-between gap-2 py-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{item.label}</p>
                    <ul className="text-xs text-muted">
                      {item.findings.map((f) => (
                        <li key={`${f.rule}-${f.field ?? ""}`}>
                          {t(`severity.${f.severity}`)} {f.rule}: {f.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <Link className={ui.buttonSm} href={`${HREF[item.entity_type]}${item.entity_id}`}>
                    {t("open")}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
