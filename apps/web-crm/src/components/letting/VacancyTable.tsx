import Link from "next/link";
import { useTranslations } from "next-intl";

import { formatDate, formatDecimal, formatEur } from "@/lib/format";

import { VacancyMeasure } from "./VacancyMeasure";

export type VacancyRow = {
  unit_id: string;
  property_number: string;
  unit_number: string;
  unit_type: string;
  living_area_sqm?: string | null;
  vacant_since?: string | null;
  vacant_days?: number | null;
  // Maßnahmen (M26-04), optional for older responses.
  status?: string;
  follow_up_on?: string | null;
  follow_up_due?: boolean;
  target_rent?: string | null;
  monthly_costs?: string | null;
  lost_rent?: string | null;
  vacancy_costs?: string | null;
  note?: string | null;
};

/** Leerstandsliste (M26): vacant since the day after the last tenancy, else unknown. */
export function VacancyTable({
  rows,
  canEdit = false,
  canCreateListing = false,
}: {
  rows: VacancyRow[];
  canEdit?: boolean;
  canCreateListing?: boolean;
}) {
  const t = useTranslations("Letting");
  if (rows.length === 0) return <p className="text-sm text-muted">{t("noVacancies")}</p>;
  return (
    <div className="overflow-x-auto">
<table className="mhvp-table">
      <thead>
        <tr>
          <th>{t("property")}</th>
          <th>{t("unit")}</th>
          <th>{t("area")}</th>
          <th>{t("since")}</th>
          <th>{t("days")}</th>
          <th>{t("targetRent")}</th>
          <th>{t("lostRent")}</th>
          <th>{t("vacancyCosts")}</th>
          <th>{t("followUp")}</th>
          <th>{t("measure")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.unit_id}>
            <td>{v.property_number}</td>
            <td>
              <Link href={`/vermietung/einheit/${v.unit_id}`} className="hover:underline">
                {v.unit_number}
              </Link>
            </td>
            <td className="tabular-nums">
              {v.living_area_sqm ? `${formatDecimal(v.living_area_sqm, 2)} m²` : t("unknown")}
            </td>
            <td>{v.vacant_since ? formatDate(v.vacant_since) : t("unknown")}</td>
            <td className="tabular-nums">{v.vacant_days ?? t("unknown")}</td>
            <td className="tabular-nums">{v.target_rent ? formatEur(v.target_rent) : "–"}</td>
            <td className="tabular-nums">{v.lost_rent ? formatEur(v.lost_rent) : "–"}</td>
            <td className="tabular-nums">{v.vacancy_costs ? formatEur(v.vacancy_costs) : "–"}</td>
            <td className={v.follow_up_due ? "font-semibold" : undefined}>
              {v.follow_up_on ? formatDate(v.follow_up_on) : "–"}
            </td>
            <td>
              <VacancyMeasure
                unitId={v.unit_id}
                status={v.status ?? "open"}
                targetRent={v.target_rent ?? null}
                monthlyCosts={v.monthly_costs ?? null}
                followUpOn={v.follow_up_on ?? null}
                note={v.note ?? null}
                canEdit={canEdit}
                canCreateListing={canCreateListing}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
</div>
  );
}
