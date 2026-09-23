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
    <table className="w-full border-collapse text-sm">
      <thead className="border-b border-border text-left text-xs text-muted">
        <tr>
          <th className="py-1.5 pr-3 font-medium">{t("account")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("due")}</th>
          <th className="py-1.5 pr-3 text-right font-medium">{t("amount")}</th>
          <th className="py-1.5 text-right font-medium">{t("remaining")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-b border-border">
            <td className="py-1.5 pr-3">{r.account_number}</td>
            <td className="py-1.5 pr-3">{formatDate(r.due_date)}</td>
            <td className="py-1.5 pr-3 text-right tabular-nums">{formatEur(r.amount)}</td>
            <td className="py-1.5 text-right tabular-nums">{formatEur(r.remaining)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="font-medium">
          <td className="py-1.5 pr-3" colSpan={3}>
            {t("total")}
          </td>
          <td className="py-1.5 text-right tabular-nums" data-testid="open-total">
            {formatEur(total.toFixed(2))}
          </td>
        </tr>
      </tfoot>
    </table>
  );
}
