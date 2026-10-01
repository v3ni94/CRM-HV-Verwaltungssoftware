"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { API, type ExportRequirement } from "@/lib/immoware";
import { ui } from "@/lib/ui";

/** Status of the exports the import needs, per report type (AE37, Q08-01). Read only. */
export function ExportRequirements() {
  const t = useTranslations("Immoware24");
  const [items, setItems] = useState<ExportRequirement[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void bff<ExportRequirement[]>(`${API}/export-requirements`).then((res) => {
      if (!active) return;
      if (res.ok && Array.isArray(res.data)) setItems(res.data);
      else if (!res.ok) setError(res.message);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="export-requirements-title">
      <h2 id="export-requirements-title" className="text-sm font-semibold">
        {t("detect.requirementsTitle")}
      </h2>
      <p className="text-sm text-muted">{t("detect.requirementsIntro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {items ? (
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="export-requirements">
            <thead>
              <tr>
                <th>{t("detect.colReport")}</th>
                <th>{t("detect.colSource")}</th>
                <th>{t("detect.colRequired")}</th>
                <th>{t("detect.colFiles")}</th>
                <th>{t("detect.colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.report_type}>
                  <td>{t(`report.${item.report_type}`)}</td>
                  <td>{item.source}</td>
                  <td className={ui.num}>
                    {item.required_fields.length
                      ? t("detect.requiredCovered", { covered: item.required_covered.length, total: item.required_fields.length })
                      : t("detect.noRequired")}
                  </td>
                  <td className={ui.num}>{item.files}</td>
                  <td>
                    <span className={ui.badge}>{t(`detect.requirement.${item.status}`)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
