"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Row = {
  cost_item_id: string;
  label: string;
  operating_cost_type: string | null;
  contract_id: string | null;
  unit_number: string | null;
  state: "missing" | "expired" | "no_type" | "excluded" | "agreed";
  blocking: boolean;
  hint: string;
};
type Report = { complete: boolean; blocking_enabled: boolean; missing_count: number; rows: Row[]; source: string };

/** Report of missing allocation bases per cost position and tenancy (M17-01, AE17). While the
 *  tenant switch is on, a gap blocks the output of the statement; the agreement itself is
 *  recorded on the contract. */
export function AllocationBasisReport({ id }: { id: string }) {
  const t = useTranslations("Billing.allocationBasis");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void bff<Report>(`/api/bff/statements/${id}/allocation-basis-report`).then((res) => {
      if (!active) return;
      if (res.ok) setReport(res.data);
      else setError(res.message);
    });
    return () => {
      active = false;
    };
  }, [id]);

  const gaps = report?.rows.filter((r) => r.blocking) ?? [];
  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report && report.complete ? <p className={`${ui.help} mt-2`}>{t("complete")}</p> : null}
      {report && !report.complete ? (
        <p role="alert" className={ui.alert}>
          {report.blocking_enabled ? t("blocked", { count: report.missing_count }) : t("notBlocked", { count: report.missing_count })}
        </p>
      ) : null}
      {gaps.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {gaps.map((r, i) => (
            <li key={`${r.cost_item_id}-${r.contract_id ?? "x"}-${i}`} className="flex items-start gap-2 text-sm">
              <span className={ui.badgeWarning}>{t(`state.${r.state}`)}</span>
              <span>
                {r.label}
                {r.unit_number ? ` (${t("unit", { unit: r.unit_number })})` : ""}: {r.hint}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {report ? <p className={`${ui.help} mt-2`}>{t("source", { source: report.source })}</p> : null}
    </section>
  );
}
