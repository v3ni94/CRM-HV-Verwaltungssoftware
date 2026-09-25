import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatEur } from "@/lib/format";

export type LiquidityAccountRow = { number: string; name: string; balance: string; kind: string };

export type LiquiditySnapshot = {
  as_of: string;
  horizon: string;
  accounts: LiquidityAccountRow[];
  free_funds: string;
  reserve_funds: string;
  segregated_deposits: string;
  expected_inflows: string;
  expected_outflows: string;
  projected_free_funds: string;
  note: string;
};

/** Liquiditätsvorschau 90 Tage (7.5): freie Mittel, Rücklagen und Mietkautionen getrennt;
 *  offene Forderungen sind keine vorhandene Liquidität. */
export function LiquidityReport({ data }: { data: LiquiditySnapshot | null }) {
  const t = useTranslations("Accounting");
  if (!data || data.accounts.length === 0) {
    return <EmptyState title={t("reports.liquidity.empty")} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.freeFunds")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.free_funds)}</dd>
        </div>
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.reserveFunds")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.reserve_funds)}</dd>
        </div>
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.segregatedDeposits")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.segregated_deposits)}</dd>
        </div>
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.expectedInflows")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.expected_inflows)}</dd>
        </div>
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.expectedOutflows")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.expected_outflows)}</dd>
        </div>
        <div className="rounded-md border border-border bg-bg p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.projectedFreeFunds")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.projected_free_funds)}</dd>
        </div>
      </dl>
      <p className="text-xs text-subtle">
        {t("reports.liquidity.horizon", { asOf: formatDate(data.as_of), horizon: formatDate(data.horizon) })}
      </p>
      <p className="text-xs text-subtle">{data.note}</p>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("account")}</th>
              <th>{t("reports.liquidity.kind")}</th>
              <th className="num">{t("balance")}</th>
            </tr>
          </thead>
          <tbody>
            {data.accounts.map((a) => (
              <tr key={a.number}>
                <td>
                  {a.number} {a.name}
                </td>
                <td>{t(`reports.liquidity.kinds.${a.kind}`)}</td>
                <td className="num">{formatEur(a.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
