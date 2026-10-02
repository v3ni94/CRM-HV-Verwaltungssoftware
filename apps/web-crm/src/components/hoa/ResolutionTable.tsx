import { useTranslations } from "next-intl";

import { ResolutionMajorityCheck } from "@/components/aj17/ResolutionMajorityCheck";
import { MajorityCheckLine, type MajorityCheck } from "@/components/hoa/MajorityCheckLine";
import { formatDate } from "@/lib/format";

export type ResolutionRow = {
  id: string;
  number: number;
  decided_on: string;
  subject: string;
  status: string;
  kind: string;
  majority_basis?: string | null;
  majority_check?: MajorityCheck | null;
  allowed_majority?: string | null;
  vote_deadline_at?: string | null;
  location?: string | null;
  court_notes?: string | null;
  entered_at?: string | null;
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
            <td>
              {r.subject}
              {r.kind === "circular" && r.allowed_majority ? (
                <span className="block text-xs text-muted" data-testid="circular-majority">
                  {t("allowedMajority")}: {r.allowed_majority === "simple" || r.allowed_majority === "unanimous" ? t(`majorities.${r.allowed_majority}`) : r.allowed_majority}
                  {r.vote_deadline_at ? ` · ${t("voteDeadline")}: ${formatDate(r.vote_deadline_at)}` : ""}
                </span>
              ) : null}
              {r.majority_check ? <MajorityCheckLine check={r.majority_check} /> : null}
              <ResolutionMajorityCheck resolutionId={r.id} />
              {r.location || r.entered_at ? (
                <span className="block text-xs text-muted" data-testid="resolution-entry">
                  {r.location ? `${t("location")}: ${r.location}` : ""}
                  {r.location && r.entered_at ? " · " : ""}
                  {r.entered_at ? `${t("enteredAt")}: ${formatDate(r.entered_at)}` : ""}
                </span>
              ) : null}
              {r.court_notes ? (
                <span className="block whitespace-pre-line text-xs" data-testid="resolution-court-notes">
                  {t("courtNotes")}: {r.court_notes}
                </span>
              ) : null}
            </td>
            <td>{t(`kinds.${r.kind}`)}</td>
            <td>{t(`statuses.${r.status}`)}</td>
          </tr>
        ))}
      </tbody>
    </table>
</div>
  );
}
