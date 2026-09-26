"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type AuditExportRun = {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  period_from: string;
  period_to: string;
  rows: number;
  sha256: string | null;
  document_id: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

/** Prüfexport je Rechtsträger und Zeitraum (A26, 7.7, D55): erstellen und Liste mit Download. */
export function AuditExportPanel({
  ledgerId,
  runs,
  defaultStart,
  defaultEnd,
}: {
  ledgerId: string;
  runs: AuditExportRun[];
  defaultStart: string;
  defaultEnd: string;
}) {
  const t = useTranslations("Accounting.reports.auditExport");
  const router = useRouter();
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<AuditExportRun>("/api/bff/accounting/audit-exports", {
      method: "POST",
      body: JSON.stringify({ ledger_id: ledgerId, period_from: start, period_to: end }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (res.data.status !== "done") setNotice(t("queued"));
    router.refresh();
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-subtle">{t("description")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("start")}</span>
          <input type="date" className={ui.input} value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("end")}</span>
          <input type="date" className={ui.input} value={end} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !start || !end || end < start}>
          {busy ? t("creating") : t("create")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="text-sm text-subtle">
          {notice}
        </p>
      ) : null}
      {runs.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table" data-testid="audit-export-list">
            <thead>
              <tr>
                <th>{t("period")}</th>
                <th>{t("createdAt")}</th>
                <th>{t("status")}</th>
                <th className="num">{t("rows")}</th>
                <th>{t("sha256")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    {formatDate(r.period_from)} bis {formatDate(r.period_to)}
                  </td>
                  <td>{formatDateTime(r.created_at)}</td>
                  <td>
                    {t(`statuses.${r.status}`)}
                    {r.status === "failed" && r.error ? <span className="block text-xs text-subtle">{r.error}</span> : null}
                  </td>
                  <td className="num">{r.rows}</td>
                  <td className="font-mono text-xs" title={r.sha256 ?? ""}>
                    {r.sha256 ? `${r.sha256.slice(0, 12)}…` : ""}
                  </td>
                  <td>
                    {r.status === "done" ? (
                      <a className={ui.button} href={`/api/bff/accounting/audit-exports/${r.id}/download`} download>
                        {t("download")}
                      </a>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
