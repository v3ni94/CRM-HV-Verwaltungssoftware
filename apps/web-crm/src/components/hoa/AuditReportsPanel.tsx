"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AuditReportContent = {
  overall_status?: string;
  scope_note?: string;
  selected?: number;
  checked_count?: number;
  checked_value?: string;
  unchecked_count?: number;
  unchecked_value?: string;
  findings?: string | null;
  recommendation?: string | null;
  date?: string;
};

export type AuditReport = {
  id: string;
  version: number;
  content: AuditReportContent;
  board_statement: { text: string; recorded_at: string } | null;
  created_at: string;
};

/** Prüfberichte (PÜ09, A72): create a report version from the current positions and record
 *  the statement of the board on a report as text. The statement has no release effect; the
 *  report figures stay as computed. */
export function AuditReportsPanel({ auditId, reports }: { auditId: string; reports: AuditReport[] }) {
  const t = useTranslations("HoaWork");
  const router = useRouter();
  const [findings, setFindings] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [statements, setStatements] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, body: unknown): Promise<boolean> {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    router.refresh();
    return true;
  }

  async function createReport(event: React.FormEvent) {
    event.preventDefault();
    if (!window.confirm(t("audit.reports.confirmCreate"))) return;
    const ok = await post(`audits/${auditId}/reports`, {
      findings: findings.trim() || null,
      recommendation: recommendation.trim() || null,
    });
    if (ok) {
      setFindings("");
      setRecommendation("");
    }
  }

  async function saveStatement(reportId: string) {
    const text = (statements[reportId] ?? "").trim();
    if (!text) return;
    const ok = await post(`audit-reports/${reportId}/board-statement`, { statement: text });
    if (ok) setStatements((prev) => ({ ...prev, [reportId]: "" }));
  }

  return (
    <section className="flex flex-col gap-3" data-testid="audit-reports">
      <h2 className={ui.h2}>{t("audit.reports.title")}</h2>
      <p className={ui.help}>{t("audit.reports.hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {reports.length === 0 ? <p className="text-sm text-muted">{t("audit.reports.none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {reports.map((r) => (
          <li key={r.id} className={`${ui.card} flex flex-col gap-2 text-sm`} data-testid="audit-report">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t("audit.reports.version", { n: r.version })}</span>
              <span className="text-xs text-subtle">{formatDateTime(r.created_at)}</span>
              {r.content.overall_status ? <span className={ui.badge}>{r.content.overall_status}</span> : null}
            </div>
            <p className="text-muted">
              {t("audit.reports.figures", {
                selected: r.content.selected ?? 0,
                checked: r.content.checked_count ?? 0,
                checkedValue: formatEur(r.content.checked_value ?? "0"),
                unchecked: r.content.unchecked_count ?? 0,
                uncheckedValue: formatEur(r.content.unchecked_value ?? "0"),
              })}
            </p>
            {r.content.scope_note ? <p className="text-xs text-subtle">{r.content.scope_note}</p> : null}
            {r.content.findings ? (
              <p>
                <span className={ui.label}>{t("audit.reports.findings")}</span> {r.content.findings}
              </p>
            ) : null}
            {r.content.recommendation ? (
              <p>
                <span className={ui.label}>{t("audit.reports.recommendation")}</span> {r.content.recommendation}
              </p>
            ) : null}
            {r.board_statement ? (
              <p className={ui.notice}>
                <span className={ui.label}>
                  {t("audit.reports.boardStatement")} ({formatDate(r.board_statement.recorded_at)})
                </span>
                <br />
                {r.board_statement.text}
              </p>
            ) : null}
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-1 flex-col gap-1">
                <span className={ui.label}>{r.board_statement ? t("audit.reports.replaceStatement") : t("audit.reports.boardStatement")}</span>
                <textarea className={ui.input} rows={2} value={statements[r.id] ?? ""} onChange={(e) => setStatements((prev) => ({ ...prev, [r.id]: e.target.value }))} />
              </label>
              <button type="button" className={ui.buttonSm} disabled={busy || !(statements[r.id] ?? "").trim()} onClick={() => void saveStatement(r.id)}>
                {t("audit.reports.saveStatement")}
              </button>
            </div>
            <p className={ui.help}>{t("audit.reports.statementHint")}</p>
          </li>
        ))}
      </ul>
      <form onSubmit={createReport} className="flex flex-col gap-2">
        <h3 className="font-medium">{t("audit.reports.create")}</h3>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.reports.findings")}</span>
          <textarea className={ui.input} rows={3} value={findings} onChange={(e) => setFindings(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("audit.reports.recommendation")}</span>
          <textarea className={ui.input} rows={2} value={recommendation} onChange={(e) => setRecommendation(e.target.value)} />
        </label>
        <div>
          <button type="submit" className={ui.button} disabled={busy}>
            {t("audit.reports.submit")}
          </button>
        </div>
      </form>
    </section>
  );
}
