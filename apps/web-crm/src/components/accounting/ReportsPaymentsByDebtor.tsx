import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/EmptyState";
import { formatEur } from "@/lib/format";

export type PaymentsByDebtorRow = { number: string; name: string; settled: string };

/** Zahlungen je Debitor im gewählten Zeitraum (7.5): Ausgleiche offener Forderungen je
 *  Debitorenkonto. Tabelle ab sm, Kartenliste darunter. */
export function PaymentsByDebtor({ rows }: { rows: PaymentsByDebtorRow[] }) {
  const t = useTranslations("Accounting");
  if (rows.length === 0) {
    return <EmptyState title={t("reports.paymentsByDebtor.empty")} />;
  }
  const total = rows.reduce((s, r) => s + Math.round(Number(r.settled) * 100), 0) / 100;
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2 sm:hidden" data-testid="payments-by-debtor-cards">
        {rows.map((r) => (
          <li key={r.number} className="rounded-md border border-border bg-bg p-3">
            <p className="text-sm font-medium text-fg">
              {r.number} {r.name}
            </p>
            <p className="text-sm tabular-nums text-muted">{formatEur(r.settled)}</p>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto sm:block">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("account")}</th>
              <th className="num">{t("reports.paymentsByDebtor.settled")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.number}>
                <td>
                  {r.number} {r.name}
                </td>
                <td className="num">{formatEur(r.settled)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-medium">
              <td>{t("reports.paymentsByDebtor.total")}</td>
              <td className="num" data-testid="payments-by-debtor-total">
                {formatEur(total.toFixed(2))}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
