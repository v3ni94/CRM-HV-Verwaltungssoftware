import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/ui/EmptyState";
import { formatDate, formatEur } from "@/lib/format";

export type SubledgerRow = {
  account_id: string;
  number: string;
  name: string;
  category: "debtor" | "creditor" | string;
  ledger_balance: string;
  open_items_remaining: string;
  difference: string;
  excluded_written_off?: string;
  excluded_written_off_count?: number;
  excluded_reversed?: string;
  excluded_reversed_count?: number;
};

export type SubledgerExcluded = {
  exclude_written_off: boolean;
  written_off: { count: number; amount: string };
  reversed: { count: number; amount: string };
};

const hasDifference = (r: SubledgerRow) => Number(r.difference) !== 0;

/** Nebenbuchabgleich der Konsistenzprüfung (B09, GA05-03): je Debitor und Kreditor Saldo des
 *  Hauptbuchs gegen offene Posten zum Stichtag. Eine Differenz ist ein Prüfhinweis, kein Fehler
 *  (nicht zugeordnete Zahlungen oder Buchungen ohne offenen Posten). */
export function SubledgerCheck({
  asOf,
  rows,
  excluded,
}: {
  asOf: string;
  rows: SubledgerRow[];
  excluded?: SubledgerExcluded;
}) {
  const t = useTranslations("Accounting.reports.subledger");
  const sections: { key: "debtor" | "creditor"; rows: SubledgerRow[] }[] = [
    { key: "debtor", rows: rows.filter((r) => r.category === "debtor") },
    { key: "creditor", rows: rows.filter((r) => r.category === "creditor") },
  ];
  const differences = rows.filter(hasDifference).length;
  return (
    <div className="flex flex-col gap-3" data-testid="subledger-check">
      <p className="text-sm text-subtle">{t("description", { date: formatDate(asOf) })}</p>
      <p role="status" className="text-sm font-medium" data-testid="subledger-summary">
        {differences === 0 ? t("noDifferences") : t("differences", { count: differences })}
      </p>
      {excluded && (excluded.written_off.count > 0 || excluded.reversed.count > 0) ? (
        <p className="text-sm text-subtle" data-testid="subledger-excluded">
          {excluded.exclude_written_off
            ? t("excludedNote", {
                writtenOff: excluded.written_off.count,
                reversed: excluded.reversed.count,
                writtenOffAmount: formatEur(excluded.written_off.amount),
                reversedAmount: formatEur(excluded.reversed.amount),
              })
            : t("includedNote", {
                writtenOff: excluded.written_off.count,
                reversed: excluded.reversed.count,
              })}
        </p>
      ) : null}
      {sections.map((s) => (
        <section key={s.key} className="flex flex-col gap-2" data-testid={`subledger-${s.key}`}>
          <h3 className="text-sm font-semibold text-fg">{t(`sections.${s.key}`)}</h3>
          {s.rows.length === 0 ? (
            <EmptyState title={t("empty")} />
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("account")}</th>
                    <th className="num">{t("ledgerBalance")}</th>
                    <th className="num">{t("openItems")}</th>
                    <th className="num">{t("difference")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rows.map((r) => (
                    <tr key={r.account_id} data-difference={hasDifference(r) ? "yes" : "no"}>
                      <td>
                        {r.number} {r.name}
                      </td>
                      <td className="num">{formatEur(r.ledger_balance)}</td>
                      <td className="num">{formatEur(r.open_items_remaining)}</td>
                      <td className={hasDifference(r) ? "num font-semibold text-danger" : "num"}>
                        {formatEur(r.difference)}
                        {hasDifference(r) ? <span className="sr-only"> {t("toReview")}</span> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
