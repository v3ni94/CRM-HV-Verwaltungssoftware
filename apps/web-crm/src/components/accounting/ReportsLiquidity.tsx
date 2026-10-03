import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { ReportHeader } from "./reportViews";

export type LiquidityAccountRow = {
  number: string;
  name: string;
  balance: string;
  kind: string;
  /** GAH-104: "bank_account", "number_convention" or "default". */
  kind_basis?: string;
};

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
  /** GAK-102: credit balances of debtors (overpayments), bound funds deducted from the projection. */
  debtor_credits?: string;
  note: string;
  /** Common report header of GET /reports/liquidity (7.7 Absatz 1). */
  header?: ReportHeader;
};

/** Liquiditätsvorschau 90 Tage (7.5): freie Mittel, Rücklagen und Mietkautionen getrennt;
 *  offene Forderungen sind keine vorhandene Liquidität. */
export function LiquidityReport({ data, ledgerId }: { data: LiquiditySnapshot | null; ledgerId?: string }) {
  const t = useTranslations("Accounting");
  const head = useTranslations("Accounting.reports.explorer.head");
  if (!data || data.accounts.length === 0) {
    return <EmptyState title={t("reports.liquidity.empty")} />;
  }
  const header = data.header;
  const xlsxHref = ledgerId
    ? `/api/bff/accounting/ledgers/${ledgerId}/reports/xlsx?${new URLSearchParams({ report: "liquidity", as_of: data.as_of }).toString()}`
    : null;
  return (
    <div className="flex flex-col gap-4">
      {header ? (
        <div className="flex flex-col gap-1" data-testid="liquidity-header">
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <div><dt className="text-muted">{head("entity")}</dt><dd>{header.legal_entity_name ?? head("none")}</dd></div>
            <div><dt className="text-muted">{head("asOf")}</dt><dd>{header.as_of ? formatDate(header.as_of) : head("none")}</dd></div>
            <div><dt className="text-muted">{head("generated")}</dt><dd>{formatDateTime(header.generated_at)}</dd></div>
            <div><dt className="text-muted">{head("status")}</dt><dd>{header.status === "draft" ? head("draft") : header.status}</dd></div>
          </dl>
          <p className="text-xs text-muted">{header.status_note}</p>
        </div>
      ) : null}
      {xlsxHref ? (
        <div>
          <a className={ui.button} href={xlsxHref} download>
            {t("reports.liquidity.xlsx")}
          </a>
        </div>
      ) : null}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-md border border-border bg-surface p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.freeFunds")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.free_funds)}</dd>
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.reserveFunds")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.reserve_funds)}</dd>
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.segregatedDeposits")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.segregated_deposits)}</dd>
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.expectedInflows")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.expected_inflows)}</dd>
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <dt className="mhvp-label text-subtle">{t("reports.liquidity.expectedOutflows")}</dt>
          <dd className="text-lg font-semibold tabular-nums">{formatEur(data.expected_outflows)}</dd>
        </div>
        {data.debtor_credits !== undefined ? (
          <div className="rounded-md border border-border bg-surface p-3" data-testid="liquidity-debtor-credits">
            <dt className="mhvp-label text-subtle">{t("reports.liquidity.debtorCredits")}</dt>
            <dd className="text-lg font-semibold tabular-nums">{formatEur(data.debtor_credits)}</dd>
          </div>
        ) : null}
        <div className="rounded-md border border-border bg-surface p-3">
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
                <td>
                  {t(`reports.liquidity.kinds.${a.kind}`)}
                  {a.kind_basis === "number_convention" ? (
                    <span className="block text-xs text-muted">{t("reports.liquidity.numberConvention")}</span>
                  ) : null}
                </td>
                <td className="num">{formatEur(a.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
