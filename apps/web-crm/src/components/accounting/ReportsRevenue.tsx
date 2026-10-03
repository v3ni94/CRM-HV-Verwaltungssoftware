import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/EmptyState";
import { formatEur } from "@/lib/format";
import { centsToDecimal, sumCents } from "@/lib/money";

export type RevenueRow = { number: string; name: string; amount: string };

/** Erträge je Erlöskonto im gewählten Zeitraum (7.5). */
export function RevenueReport({ rows }: { rows: RevenueRow[] }) {
  const t = useTranslations("Accounting");
  if (rows.length === 0) {
    return <EmptyState title={t("reports.revenue.empty")} />;
  }
  const total = centsToDecimal(sumCents(rows.map((r) => r.amount)) ?? 0n);
  return (
    <div className="overflow-x-auto">
      <table className="mhvp-table">
        <thead>
          <tr>
            <th>{t("account")}</th>
            <th className="num">{t("reports.revenue.amount")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.number}>
              <td>
                {r.number} {r.name}
              </td>
              <td className="num">{formatEur(r.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-medium">
            <td>{t("reports.revenue.total")}</td>
            <td className="num" data-testid="revenue-total">
              {formatEur(total)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
