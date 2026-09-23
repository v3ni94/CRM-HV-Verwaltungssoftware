import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";

export type ResolutionRow = {
  id: string;
  number: number;
  decided_on: string;
  subject: string;
  status: string;
  kind: string;
  majority_basis?: string | null;
};

/** Beschluss-Sammlung (M24, M25): number, date, subject, status; read only. */
export function ResolutionTable({ rows }: { rows: ResolutionRow[] }) {
  const t = useTranslations("Hoa");
  if (rows.length === 0) return <p className="text-sm text-muted">{t("noResolutions")}</p>;
  return (
    <table className="w-full border-collapse text-sm">
      <thead className="border-b border-border text-left text-xs text-muted">
        <tr>
          <th className="py-1.5 pr-3 font-medium">{t("number")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("decidedOn")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("subject")}</th>
          <th className="py-1.5 pr-3 font-medium">{t("kind")}</th>
          <th className="py-1.5 font-medium">{t("status")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className="border-b border-border">
            <td className="py-1.5 pr-3 tabular-nums">{r.number}</td>
            <td className="py-1.5 pr-3">{formatDate(r.decided_on)}</td>
            <td className="py-1.5 pr-3">{r.subject}</td>
            <td className="py-1.5 pr-3">{t(`kinds.${r.kind}`)}</td>
            <td className="py-1.5">{t(`statuses.${r.status}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
