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
    <div className="overflow-x-auto">
<table className="mhvp-table">
      <thead>
        <tr>
          <th>{t("number")}</th>
          <th>{t("decidedOn")}</th>
          <th>{t("subject")}</th>
          <th>{t("kind")}</th>
          <th>{t("status")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td className="tabular-nums">{r.number}</td>
            <td>{formatDate(r.decided_on)}</td>
            <td>{r.subject}</td>
            <td>{t(`kinds.${r.kind}`)}</td>
            <td>{t(`statuses.${r.status}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
</div>
  );
}
