"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { formatBytes } from "@/lib/mailText";
import { ui } from "@/lib/ui";

type ExportJob = {
  id: string;
  status: "queued" | "running" | "ready" | "failed" | "expired";
  expires_at?: string | null;
  created_at: string;
  size: number | null;
  error: string | null;
  documents_failed: number | null;
};

/** M2-01: full tenant export as a background job (`/tenant/export-jobs`). Start, status list and
 *  download are for the tenant administrator only (the API enforces it); every start and every
 *  download is written to the event log. */
export function TenantExportJobs({ canStart }: { canStart: boolean }) {
  const t = useTranslations("TenantExportJobs");
  const [jobs, setJobs] = useState<ExportJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!canStart) return;
    const res = await bff<ExportJob[]>("/api/bff/tenant/export-jobs");
    if (res.ok) setJobs(res.data);
    else setError(res.message);
  }, [canStart]);

  useEffect(() => {
    void load();
  }, [load]);

  async function start() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<ExportJob>("/api/bff/tenant/export-jobs", {
      method: "POST",
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("started"));
      await load();
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="tenant-export-jobs-title">
      <div className="flex flex-col gap-3">
        <h2 id="tenant-export-jobs-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        {canStart ? (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={ui.secondary}
              disabled={busy}
              onClick={() => void start()}
            >
              {t("start")}
            </button>
            <button
              type="button"
              className={ui.secondary}
              disabled={busy}
              onClick={() => void load()}
            >
              {t("refresh")}
            </button>
          </div>
        ) : (
          <p className={ui.help}>{t("readOnly")}</p>
        )}
        {message ? (
          <span className="text-xs text-success-fg">{message}</span>
        ) : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {canStart && jobs.length === 0 ? (
          <p className={ui.help}>{t("empty")}</p>
        ) : null}
        {jobs.length > 0 ? (
          <div className={ui.tableScroll}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("created")}</th>
                  <th>{t("status")}</th>
                  <th>{t("size")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} data-testid="export-job-row">
                    <td>{formatDateTime(job.created_at)}</td>
                    <td>
                      {t(
                        `status${job.status.charAt(0).toUpperCase()}${job.status.slice(1)}` as "statusReady",
                      )}
                      {job.status === "ready" && job.expires_at ? (
                        <span className={ui.help}>
                          {" "}
                          {t("expiresAt", { date: formatDateTime(job.expires_at) })}
                        </span>
                      ) : null}
                      {job.error ? (
                        <span className={ui.help}> {job.error}</span>
                      ) : null}
                      {job.documents_failed ? (
                        <span className={ui.help}>
                          {" "}
                          {t("documentsFailed", {
                            count: job.documents_failed,
                          })}
                        </span>
                      ) : null}
                    </td>
                    <td>{formatBytes(job.size)}</td>
                    <td>
                      {job.status === "ready" ? (
                        <a
                          className={ui.secondary}
                          href={`/api/bff/tenant/export-jobs/${job.id}/download`}
                        >
                          {t("download")}
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
