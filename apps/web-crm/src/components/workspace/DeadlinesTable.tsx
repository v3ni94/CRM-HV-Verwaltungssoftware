import { useTranslations } from "next-intl";
import Link from "next/link";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Row of GET /api/v1/workspace/deadlines (A41). */
export type Deadline = {
  id: string;
  kind: string;
  source_type: string;
  source_id: string;
  reference: string;
  due_on: string;
  lead_days: number;
  status: string;
  property_id: string | null;
  notified_at: string | null;
  done_at: string | null;
  updated_at: string;
  /** Route to the source row (P1 AP7), null when the source has no page. */
  href?: string | null;
};

export function DeadlinesTable({ rows }: { rows: Deadline[] }) {
  const t = useTranslations("Deadlines");
  if (rows.length === 0) return <p className={`${ui.card} text-sm text-muted`}>{t("empty")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className={ui.table} data-testid="deadlines-table">
        <thead>
          <tr>
            <th scope="col">{t("column.due_on")}</th>
            <th scope="col">{t("column.kind")}</th>
            <th scope="col">{t("column.reference")}</th>
            <th scope="col">{t("column.lead_days")}</th>
            <th scope="col">{t("column.status")}</th>
            <th scope="col">{t("column.notified_at")}</th>
            <th scope="col">{t("column.source")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td className="tabular-nums">
                {formatDate(row.due_on)} <span className={ui.badge}>{t("toCheck")}</span>
              </td>
              <td>{t.has(`kind.${row.kind}`) ? t(`kind.${row.kind}`) : row.kind}</td>
              <td>{row.reference}</td>
              <td className="tabular-nums">{t("days", { count: row.lead_days })}</td>
              <td>
                <span className={row.status === "open" ? ui.badgeWarning : ui.badgeSuccess}>
                  {t.has(`status.${row.status}`) ? t(`status.${row.status}`) : row.status}
                </span>
              </td>
              <td className="tabular-nums">{formatDate(row.notified_at)}</td>
              <td>
                {row.href ? (
                  <Link href={row.href} className="underline">
                    {t("openSource")}
                  </Link>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
