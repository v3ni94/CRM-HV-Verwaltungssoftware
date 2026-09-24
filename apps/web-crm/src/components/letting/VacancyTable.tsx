import Link from "next/link";
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
    <div className="overflow-x-auto">
<table className="mhvp-table">
      <thead>
        <tr>
          <th>{t("property")}</th>
          <th>{t("unit")}</th>
          <th>{t("area")}</th>
          <th>{t("since")}</th>
          <th>{t("days")}</th>
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
          </tr>
        ))}
      </tbody>
    </table>
</div>
  );
}
