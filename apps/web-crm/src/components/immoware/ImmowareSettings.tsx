"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ImmowareConnection = {
  base_url: string | null;
  carddav_url: string | null;
  caldav_url: string | null;
  webdav_root_url: string | null;
  carddav_url_discovered: boolean;
  caldav_url_discovered: boolean;
  webdav_root_discovered: boolean;
  username: string | null;
  has_password: boolean;
  enabled: boolean;
  verify_tls: boolean;
  poll_minutes: number;
  last_check_at: string | null;
  last_check_ok: boolean | null;
  last_error: string | null;
  last_diagnosis: DiagnosisResult | null;
  last_diagnosis_at: string | null;
};

export type DiagnosisStep = {
  name: string;
  url: string;
  status: number | null;
  ok: boolean;
  note: string;
  collections: string[];
};

export type DiagnosisResult = {
  steps: DiagnosisStep[];
  carddav_url: string | null;
  caldav_url: string | null;
  webdav_url: string | null;
  dav_module_likely_not_booked: boolean;
};

export type ImmowareSyncRun = {
  id: string;
  kind: "webdav" | "carddav" | "caldav";
  started_at: string;
  finished_at: string | null;
  status: "running" | "success" | "error";
  seen: number;
  added: number;
  changed: number;
  removed: number;
  error: string | null;
};

const SYNC_KINDS = ["webdav", "carddav", "caldav"] as const;

/** Immoware24-Anbindung (Einstellungen, M32): Verbindungsdaten pflegen, Verbindung pruefen und
 *  Abholung je DAV-Art manuell anstossen. Immoware24 bleibt Master, der Hub liest ausschliesslich
 *  per WebDAV, CardDAV und CalDAV; es gibt keinen Schreibpfad in dieser Ansicht. */
export function ImmowareSettings({
  connection,
  runs: initialRuns,
  canManage,
}: {
  connection: ImmowareConnection;
  runs: ImmowareSyncRun[];
  canManage: boolean;
}) {
  const t = useTranslations("ImmowareSettings");
  const [saved, setSaved] = useState(connection);
  const [enabled, setEnabled] = useState(connection.enabled);
  const [baseUrl, setBaseUrl] = useState(connection.base_url ?? "");
  const [carddavUrl, setCarddavUrl] = useState(connection.carddav_url ?? "");
  const [caldavUrl, setCaldavUrl] = useState(connection.caldav_url ?? "");
  const [username, setUsername] = useState(connection.username ?? "");
  const [password, setPassword] = useState("");
  const [verifyTls, setVerifyTls] = useState(connection.verify_tls);
  const [pollMinutes, setPollMinutes] = useState(connection.poll_minutes);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [checkBusy, setCheckBusy] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);

  const [diagnoseBusy, setDiagnoseBusy] = useState(false);
  const [diagnoseError, setDiagnoseError] = useState<string | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(connection.last_diagnosis);

  const [syncBusy, setSyncBusy] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [runs, setRuns] = useState<ImmowareSyncRun[]>(initialRuns);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    const body = {
      enabled,
      base_url: baseUrl.trim() || null,
      carddav_url: carddavUrl.trim() || null,
      caldav_url: caldavUrl.trim() || null,
      username: username.trim() || null,
      verify_tls: verifyTls,
      poll_minutes: pollMinutes,
      ...(password ? { password } : {}),
    };
    setBusy(true);
    const res = await bff<ImmowareConnection>("/api/bff/immoware/connection", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(res.data);
    setPassword("");
    setMessage(t("saved"));
  };

  const check = async () => {
    setCheckError(null);
    setCheckBusy(true);
    const res = await bff<ImmowareConnection>("/api/bff/immoware/connection/check", { method: "POST" });
    setCheckBusy(false);
    if (!res.ok) return setCheckError(res.message);
    setSaved(res.data);
  };

  const diagnose = async () => {
    setDiagnoseError(null);
    setDiagnoseBusy(true);
    const res = await bff<DiagnosisResult>("/api/bff/immoware/connection/diagnose", { method: "POST" });
    setDiagnoseBusy(false);
    if (!res.ok) return setDiagnoseError(res.message);
    setDiagnosis(res.data);
    const conn = await bff<ImmowareConnection>("/api/bff/immoware/connection");
    if (conn.ok) setSaved(conn.data);
  };

  const applyDiscovered = (kind: "carddav" | "caldav" | "webdav", url: string) => {
    if (kind === "carddav") setCarddavUrl(url);
    else if (kind === "caldav") setCaldavUrl(url);
    else setBaseUrl(url);
  };

  const triggerSync = async (kind: (typeof SYNC_KINDS)[number]) => {
    setSyncError(null);
    setSyncBusy(kind);
    const res = await bff<{ run_id: string }>(`/api/bff/immoware/sync/${kind}`, { method: "POST" });
    setSyncBusy(null);
    if (!res.ok) {
      setSyncError(res.message);
      return;
    }
    const list = await bff<ImmowareSyncRun[]>("/api/bff/immoware/sync/runs");
    if (list.ok) setRuns(list.data);
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={save} className={`${ui.card} flex flex-col gap-4`} aria-label={t("connectionTitle")}>
        <h2 className={ui.h2}>{t("connectionTitle")}</h2>
        <p className="text-sm text-muted">{t("hint")}</p>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} disabled={!canManage} />
          {t("enabled")}
        </label>

        <div>
          <label htmlFor="imw-base-url" className={ui.label}>
            {t("baseUrl")}
          </label>
          <input
            id="imw-base-url"
            type="url"
            className={ui.input}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://iris.awi-rems.de/webdav"
            disabled={!canManage}
          />
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="imw-carddav-url" className={ui.label}>
              {t("carddavUrl")}
            </label>
            <input
              id="imw-carddav-url"
              type="url"
              className={ui.input}
              value={carddavUrl}
              onChange={(e) => setCarddavUrl(e.target.value)}
              disabled={!canManage}
            />
          </div>
          <div>
            <label htmlFor="imw-caldav-url" className={ui.label}>
              {t("caldavUrl")}
            </label>
            <input
              id="imw-caldav-url"
              type="url"
              className={ui.input}
              value={caldavUrl}
              onChange={(e) => setCaldavUrl(e.target.value)}
              disabled={!canManage}
            />
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="imw-username" className={ui.label}>
              {t("username")}
            </label>
            <input
              id="imw-username"
              className={ui.input}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={!canManage}
            />
          </div>
          <div>
            <label htmlFor="imw-password" className={ui.label}>
              {t("password")}
            </label>
            <input
              id="imw-password"
              type="password"
              autoComplete="off"
              className={ui.input}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={saved.has_password ? t("passwordStored") : t("passwordMissing")}
              disabled={!canManage}
            />
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={verifyTls} onChange={(e) => setVerifyTls(e.target.checked)} disabled={!canManage} />
            {t("verifyTls")}
          </label>
          <div>
            <label htmlFor="imw-poll-minutes" className={ui.label}>
              {t("pollMinutes")}
            </label>
            <input
              id="imw-poll-minutes"
              type="number"
              min={1}
              max={1440}
              className={ui.input}
              value={pollMinutes}
              onChange={(e) => setPollMinutes(Number(e.target.value) || 1)}
              disabled={!canManage}
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {message ? <p className={ui.success}>{message}</p> : null}

        {canManage ? (
          <div className={ui.formActions}>
            <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
              {t("save")}
            </button>
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={check} disabled={checkBusy}>
              {t("check")}
            </button>
            <button
              type="button"
              className={`${ui.button} ${ui.actionFull}`}
              onClick={diagnose}
              disabled={diagnoseBusy}
            >
              {diagnoseBusy ? t("diagnose.running") : t("diagnose.button")}
            </button>
          </div>
        ) : null}

        {checkError ? (
          <p role="alert" className={ui.alert}>
            {checkError}
          </p>
        ) : null}

        <div className="text-sm text-muted">
          {saved.last_check_at ? (
            <p>
              {t("lastCheck", { at: formatDateTime(saved.last_check_at) })}{" "}
              {saved.last_check_ok ? (
                <span className={ui.badgeSuccess}>{t("checkOk")}</span>
              ) : (
                <span className={ui.badgeDanger}>{t("checkFailed")}</span>
              )}
            </p>
          ) : (
            <p>{t("noCheckYet")}</p>
          )}
          {saved.last_error ? <p className="mt-1 text-xs text-danger-fg">{saved.last_error}</p> : null}
        </div>
      </form>

      {diagnoseError ? (
        <p role="alert" className={ui.alert}>
          {diagnoseError}
        </p>
      ) : null}

      {diagnosis ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("diagnose.title")}>
          <h2 className={ui.h2}>{t("diagnose.title")}</h2>
          {diagnosis.dav_module_likely_not_booked ? (
            <p role="alert" className={ui.alert}>
              {t("diagnose.notBooked")}
            </p>
          ) : null}
          <div className="flex flex-col gap-1">
            {diagnosis.carddav_url ? (
              <p className="text-sm">
                {t("diagnose.discovered.carddav", { url: diagnosis.carddav_url })}{" "}
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => applyDiscovered("carddav", diagnosis.carddav_url ?? "")}
                >
                  {t("diagnose.discovered.apply")}
                </button>
              </p>
            ) : null}
            {diagnosis.caldav_url ? (
              <p className="text-sm">
                {t("diagnose.discovered.caldav", { url: diagnosis.caldav_url })}{" "}
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => applyDiscovered("caldav", diagnosis.caldav_url ?? "")}
                >
                  {t("diagnose.discovered.apply")}
                </button>
              </p>
            ) : null}
            {diagnosis.webdav_url ? (
              <p className="text-sm">
                {t("diagnose.discovered.webdav", { url: diagnosis.webdav_url })}{" "}
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => applyDiscovered("webdav", diagnosis.webdav_url ?? "")}
                >
                  {t("diagnose.discovered.apply")}
                </button>
              </p>
            ) : null}
          </div>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="immoware-diagnosis-steps">
              <thead>
                <tr>
                  <th>{t("diagnose.columns.step")}</th>
                  <th>{t("diagnose.columns.url")}</th>
                  <th>{t("diagnose.columns.status")}</th>
                  <th>{t("diagnose.columns.note")}</th>
                </tr>
              </thead>
              <tbody>
                {diagnosis.steps.map((step, index) => (
                  <tr key={`${step.name}-${index}`}>
                    <td>{step.name}</td>
                    <td className="break-all text-xs text-muted">{step.url}</td>
                    <td className="tabular-nums">
                      {step.ok ? (
                        <span className={ui.badgeSuccess}>{step.status ?? "-"}</span>
                      ) : (
                        <span className={ui.badgeDanger}>{step.status ?? "-"}</span>
                      )}
                    </td>
                    <td className="text-xs text-muted">{step.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {canManage ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("syncTitle")}>
          <h2 className={ui.h2}>{t("syncTitle")}</h2>
          <div className="flex flex-wrap gap-2">
            {SYNC_KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                className={ui.button}
                onClick={() => triggerSync(kind)}
                disabled={syncBusy !== null}
              >
                {t(`fetchNow.${kind}`)}
              </button>
            ))}
          </div>
          {syncError ? (
            <p role="alert" className={ui.alert}>
              {syncError}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className={`${ui.card} flex flex-col gap-3 overflow-x-auto p-0`} aria-label={t("runsTitle")}>
        <h2 className={`${ui.h2} px-4 pt-4 sm:px-5`}>{t("runsTitle")}</h2>
        {runs.length === 0 ? (
          <p className="px-4 pb-4 text-sm text-muted sm:px-5">{t("runsEmpty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="immoware-runs">
              <thead>
                <tr>
                  <th>{t("columns.kind")}</th>
                  <th>{t("columns.started")}</th>
                  <th>{t("columns.finished")}</th>
                  <th>{t("columns.status")}</th>
                  <th>{t("columns.seen")}</th>
                  <th>{t("columns.added")}</th>
                  <th>{t("columns.changed")}</th>
                  <th>{t("columns.removed")}</th>
                  <th>{t("columns.error")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>{t(`fetchNow.${run.kind}`)}</td>
                    <td className="tabular-nums text-muted">{formatDateTime(run.started_at)}</td>
                    <td className="tabular-nums text-muted">{formatDateTime(run.finished_at)}</td>
                    <td>
                      {run.status === "success" ? (
                        <span className={ui.badgeSuccess}>{t("status.success")}</span>
                      ) : run.status === "error" ? (
                        <span className={ui.badgeDanger}>{t("status.error")}</span>
                      ) : (
                        <span className={ui.badge}>{t("status.running")}</span>
                      )}
                    </td>
                    <td className="tabular-nums">{run.seen}</td>
                    <td className="tabular-nums">{run.added}</td>
                    <td className="tabular-nums">{run.changed}</td>
                    <td className="tabular-nums">{run.removed}</td>
                    <td className="text-xs text-danger-fg">{run.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
