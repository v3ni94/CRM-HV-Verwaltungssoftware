import { useTranslations } from "next-intl";

import { formatDate, formatEur } from "@/lib/format";

export type OpenItem = {
  id: string;
  account_number: string;
  kind: string;
  due_date: string | null;
  amount: string;
  remaining: string;
};

/** Open items at a cut-off date (B02): remaining amount is computed from settlements. */
export function OpenItemsTable({ rows }: { rows: OpenItem[] }) {
  const t = useTranslations("Receivables");
  if (rows.length === 0) return <p className="text-sm text-muted">{t("noOpenItems")}</p>;
  const total = rows.reduce((s, r) => s + Math.round(Number(r.remaining) * 100), 0) / 100;
  return (
    <div className="overflow-x-auto">
<table className="mhvp-table">
      <thead>
        <tr>
          <th>{t("account")}</th>
          <th>{t("due")}</th>
          <th className="num">{t("amount")}</th>
          <th className="num">{t("remaining")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>{r.account_number}</td>
            <td>{formatDate(r.due_date)}</td>
            <td className="num">{formatEur(r.amount)}</td>
            <td className="num">{formatEur(r.remaining)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="font-medium">
          <td colSpan={3}>
            {t("total")}
          </td>
          <td className="num" data-testid="open-total">
            {formatEur(total.toFixed(2))}
          </td>
        </tr>
      </tfoot>
    </table>
</div>
  );
}
