import { useTranslations } from "next-intl";

import { formatEur } from "@/lib/format";

export type ReserveYearRow = {
  year: number;
  opening: string;
  contributions: string;
  contribution_basis: "paid" | "planned";
  withdrawals: string;
  taxes: string;
  fees: string;
  interest: string;
  closing: string;
  source: "statement" | "plan" | "none";
};

export type AccountOption = { id: string; label: string };

/** Development of one reserve per year (opening, contribution, withdrawal, taxes, fees, interest,
 *  closing). Display only, nothing here posts (M24-01). */
export function ReserveYearsTable({ rows, caption }: { rows: ReserveYearRow[]; caption?: string }) {
  const t = useTranslations("HoaReserves");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label={caption ?? t("yearTitle")}>
        <thead>
          <tr className="text-left">
            <th>{t("year")}</th>
            <th>{t("opening")}</th>
            <th>{t("contribution")}</th>
            <th>{t("withdrawals")}</th>
            <th>{t("taxes")}</th>
            <th>{t("fees")}</th>
            <th>{t("interest")}</th>
            <th>{t("closing")}</th>
            <th>{t("basis")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.year}>
              <td>{r.year}</td>
              <td>{formatEur(r.opening)}</td>
              <td>{formatEur(r.contributions)}</td>
              <td>{formatEur(r.withdrawals)}</td>
              <td>{formatEur(r.taxes)}</td>
              <td>{formatEur(r.fees)}</td>
              <td>{formatEur(r.interest)}</td>
              <td className="font-medium">{formatEur(r.closing)}</td>
              <td>
                {r.source === "statement" ? t("sourceStatement") : r.source === "plan" ? t("sourcePlan") : t("sourceNone")}
                {r.source !== "none" ? ` (${r.contribution_basis === "paid" ? t("basisPaid") : t("basisPlanned")})` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
