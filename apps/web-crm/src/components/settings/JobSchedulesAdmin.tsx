"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type JobSchedule = {
  job_key: string;
  label: string;
  enabled: boolean;
  run_at: string | null;
  configured: boolean;
};

/** Standardjobs je Mandant (MASTER-PROMPT 15.1, GA12-02): Schalter und Uhrzeit HH:MM über
 *  `GET/PUT /automation/job-schedules`. Das Abschalten oder Verschieben öffnet keine Sperre und
 *  kein Gate. Speichern braucht tenant_settings:update (das Backend prüft). */
export function JobSchedulesAdmin({
  initial,
  canManage,
}: {
  initial: JobSchedule[];
  canManage: boolean;
}) {
  const t = useTranslations("AutomationJobs");
  const [jobs, setJobs] = useState(initial);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function patch(key: string, change: Partial<JobSchedule>) {
    setJobs((prev) =>
      prev.map((j) => (j.job_key === key ? { ...j, ...change } : j)),
    );
  }

  async function save(job: JobSchedule) {
    setBusyKey(job.job_key);
    setMessage(null);
    setError(null);
    const res = await bff<JobSchedule>(
      `/api/bff/automation/job-schedules/${job.job_key}`,
      {
        method: "PUT",
        body: JSON.stringify({
          enabled: job.enabled,
          run_at: job.run_at ? job.run_at : null,
        }),
      },
    );
    setBusyKey(null);
    if (res.ok) {
      patch(job.job_key, { configured: true });
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className="flex flex-col gap-2" aria-label={t("title")}>
      <h2 className="text-lg font-semibold">{t("title")}</h2>
      <p className={ui.help}>{t("description")}</p>
      {error ? (
        <p role="alert" className="text-sm text-danger-fg">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.help}>
          {message}
        </p>
      ) : null}
      {jobs.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      <div className="overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("job")}</th>
              <th>{t("enabled")}</th>
              <th>{t("runAt")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_key}>
                <td>
                  {job.label}{" "}
                  <span className={ui.badge}>
                    {job.configured ? t("configured") : t("default")}
                  </span>
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${t("enabled")} ${job.label}`}
                    checked={job.enabled}
                    disabled={!canManage}
                    onChange={(e) =>
                      patch(job.job_key, { enabled: e.target.checked })
                    }
                  />
                </td>
                <td>
                  <input
                    type="time"
                    aria-label={`${t("runAt")} ${job.label}`}
                    className={ui.input}
                    value={job.run_at ?? ""}
                    disabled={!canManage}
                    title={t("runAtHelp")}
                    onChange={(e) =>
                      patch(job.job_key, { run_at: e.target.value || null })
                    }
                  />
                </td>
                <td>
                  {canManage ? (
                    <button
                      type="button"
                      className={ui.buttonSm}
                      disabled={busyKey === job.job_key}
                      onClick={() => void save(job)}
                    >
                      {t("save")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
