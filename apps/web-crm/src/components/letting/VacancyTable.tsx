import { useTranslations } from "next-intl";

import { formatDate, formatDecimal } from "@/lib/format";

export type VacancyRow = {
  unit_id: string;
  property_number: string;
  unit_number: string;
  unit_type: string;
  living_area_sqm?: string | null;
  vacant_since?: string | null;
  vacant_days?: number | null;
};

/** Leerstandsliste (M26): vacant since the day after the last tenancy, else unknown. */
export function VacancyTable({ rows }: { rows: VacancyRow[] }) {
  const t = useTranslations("Letting");
  if (rows.length === 0) return <p className="text-sm text-muted">{t("noVacancies")}</p>;
  return (
    <table className="w-full border-collapse text-sm">
      <thead className="border-b border-border text-left text-xs text-muted">
        <tr>
          <th className="py-1.5 pr-3 font-medium">{t("property")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("unit")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("area")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("since")}</th>
          <th className="py-1.5 font-medium">{t("days")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.unit_id} className="border-b border-border">
            <td className="py-1.5 pr-3">{v.property_number}</td>
            <td className="py-1.5 pr-3">{v.unit_number}</td>
            <td className="py-1.5 pr-3 tabular-nums">
              {v.living_area_sqm ? `${formatDecimal(v.living_area_sqm, 2)} m²` : t("unknown")}
            </td>
            <td className="py-1.5 pr-3">{v.vacant_since ? formatDate(v.vacant_since) : t("unknown")}</td>
            <td className="py-1.5 tabular-nums">{v.vacant_days ?? t("unknown")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
