import { useTranslations } from "next-intl";

import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type LevyInstalmentStatus = { due_month: string; charged: string; received: string; open: string };
export type LevyUnitStatus = {
  unit_id: string;
  unit_number: string;
  charged: string;
  received: string;
  open: string;
  refunds_proposed: string;
  instalments: LevyInstalmentStatus[];
};
export type LevyUsage = { journal_entry_id: string; booking_date: string; text: string; amount: string };
export type LevyPaymentStatusData = {
  units: LevyUnitStatus[];
  usage: LevyUsage[];
  usage_truncated: boolean;
  note: string;
};

/** AP21 / GAM-110: Ist und Rückstand je Einheit und Rate aus den gebuchten Forderungen, dazu die
 *  Buchungen auf dem Verwendungskonto. Nur Anzeige, nichts wird gebucht. */
export function LevyPaymentStatus({ data }: { data: LevyPaymentStatusData }) {
  const t = useTranslations("Levy");
  return (
    <section className={ui.card} data-testid="levy-payment-status">
      <h2 className={ui.h2}>{t("paymentStatus.title")}</h2>
      {data.units.length ? (
        <div className="mt-2 overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("unit")}</th>
                <th>{t("paymentStatus.instalment")}</th>
                <th className="num">{t("paymentStatus.charged")}</th>
                <th className="num">{t("paymentStatus.received")}</th>
                <th className="num">{t("paymentStatus.open")}</th>
              </tr>
            </thead>
            <tbody>
              {data.units.flatMap((u) => [
                ...u.instalments.map((i) => (
                  <tr key={`${u.unit_id}-${i.due_month}`}>
                    <td>{u.unit_number}</td>
                    <td className="tabular-nums">{formatDate(i.due_month)}</td>
                    <td className="num">{formatEur(i.charged)}</td>
                    <td className="num">{formatEur(i.received)}</td>
                    <td className="num" data-open={Number(i.open) > 0 ? "yes" : "no"}>{formatEur(i.open)}</td>
                  </tr>
                )),
                <tr key={`${u.unit_id}-sum`} className="font-medium">
                  <td>{u.unit_number}</td>
                  <td>
                    {t("paymentStatus.sum")}
                    {Number(u.refunds_proposed) > 0 ? ` · ${t("paymentStatus.refundsProposed", { amount: formatEur(u.refunds_proposed) })}` : ""}
                  </td>
                  <td className="num">{formatEur(u.charged)}</td>
                  <td className="num">{formatEur(u.received)}</td>
                  <td className="num">{formatEur(u.open)}</td>
                </tr>,
              ])}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted">{t("paymentStatus.none")}</p>
      )}
      <h3 className="mt-4 text-sm font-semibold">{t("paymentStatus.usage")}</h3>
      {data.usage.length ? (
        <ul className="mt-1 text-sm" data-testid="levy-usage">
          {data.usage.map((u) => (
            <li key={u.journal_entry_id} className="flex justify-between gap-2 tabular-nums">
              <span>
                {formatDate(u.booking_date)} {u.text}
              </span>
              <span>{formatEur(u.amount)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-muted">{t("paymentStatus.noUsage")}</p>
      )}
      {data.usage_truncated ? <p className="mt-1 text-xs text-muted">{t("paymentStatus.truncated")}</p> : null}
      <p className="mt-2 text-xs text-muted">{data.note}</p>
    </section>
  );
}
