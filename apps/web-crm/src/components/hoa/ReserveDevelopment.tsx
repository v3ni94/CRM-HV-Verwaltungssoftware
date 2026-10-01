import { getTranslations } from "next-intl/server";

import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ReservePosition = {
  reserve_id: string;
  name: string;
  purpose: string | null;
  contributions_planned: string;
  contributions_paid?: string;
  contributions_paid_bound?: boolean;
  withdrawals: string;
  taxes: string;
  fees: string;
  interest: string;
  planned_change: string;
  paid_change?: string;
  movements: { kind: string; amount: string; purpose: string; receipt_linked: boolean }[];
};

export type ReserveBlock = {
  opening: string;
  contributions_resolved: string;
  contributions_paid: string;
  contributions_paid_unassigned?: string;
  withdrawals: string;
  interest: string;
  closing: string;
  bank_balance: string;
  bank_difference: string;
  positions?: ReservePosition[];
};

/** Development of the reserves of one statement as an own block (W08, M24-01): the total block
 *  and one row per earmarked reserve with planned and paid contributions and the uses. */
export async function ReserveDevelopment({ block }: { block: ReserveBlock }) {
  const t = await getTranslations("HoaReserves");
  const total: [string, string][] = [
    [t("opening"), block.opening],
    [t("resolved"), block.contributions_resolved],
    [t("paid"), block.contributions_paid],
    [t("withdrawals"), block.withdrawals],
    [t("interest"), block.interest],
    [t("closing"), block.closing],
    [t("bankBalance"), block.bank_balance],
    [t("bankDifference"), block.bank_difference],
  ];
  const positions = block.positions ?? [];
  return (
    <section className="flex flex-col gap-3" data-testid="reserve-development">
      <h2 className={ui.h2}>{t("developmentTitle")}</h2>
      <div className="overflow-x-auto">
        <table className={ui.table}>
          <tbody>
            {total.map(([label, value]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="text-right">{formatEur(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.contributions_paid_unassigned && Number(block.contributions_paid_unassigned) !== 0 ? (
        <p className={ui.notice}>{t("unassigned", { amount: formatEur(block.contributions_paid_unassigned) })}</p>
      ) : null}
      {positions.length ? (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="reserve-positions">
            <thead>
              <tr>
                <th>{t("reserve")}</th>
                <th className="text-right">{t("planned")}</th>
                <th className="text-right">{t("paid")}</th>
                <th className="text-right">{t("withdrawals")}</th>
                <th className="text-right">{t("taxes")}</th>
                <th className="text-right">{t("fees")}</th>
                <th className="text-right">{t("interest")}</th>
                <th className="text-right">{t("change")}</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.reserve_id}>
                  <td>
                    {p.name}
                    {p.purpose ? <span className="block text-xs text-muted">{p.purpose}</span> : null}
                  </td>
                  <td className="text-right">{formatEur(p.contributions_planned)}</td>
                  <td className="text-right">{p.contributions_paid_bound ? formatEur(p.contributions_paid ?? "0") : t("notBound")}</td>
                  <td className="text-right">{formatEur(p.withdrawals)}</td>
                  <td className="text-right">{formatEur(p.taxes)}</td>
                  <td className="text-right">{formatEur(p.fees)}</td>
                  <td className="text-right">{formatEur(p.interest)}</td>
                  <td className="text-right">{formatEur(p.contributions_paid_bound ? (p.paid_change ?? p.planned_change) : p.planned_change)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
