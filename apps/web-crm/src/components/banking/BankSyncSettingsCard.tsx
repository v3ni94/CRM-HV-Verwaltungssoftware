"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type SyncSetting = { sync_hour: number; configured: boolean };
type SyncRun = { connections: number; not_configured: number; queued: number };

/** Täglicher Bankabruf (8.2, M11-05): Uhrzeit je Mandant und manueller Gesamtabruf. Der
 *  Online-Abruf braucht weiterhin die Zustimmung des jeweiligen Konnektors (finAPI). */
export function BankSyncSettingsCard({ canEdit, canRun }: { canEdit: boolean; canRun: boolean }) {
  const t = useTranslations("BankSync");
  const [hour, setHour] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bff<SyncSetting>("/api/bff/banking/sync/settings").then((r) => {
      if (r.ok) setHour(r.data.sync_hour);
      else setError(r.message);
    });
  }, []);

  async function save(next: number) {
    setBusy(true);
    setError(null);
    setMessage(null);
    const r = await bff<SyncSetting>("/api/bff/banking/sync/settings", { method: "PUT", body: JSON.stringify({ sync_hour: next }) });
    setBusy(false);
    if (r.ok) {
      setHour(r.data.sync_hour);
      setMessage(t("saved"));
    } else setError(r.message);
  }

  async function runNow() {
    setBusy(true);
    setError(null);
    setMessage(null);
    const r = await bff<SyncRun>("/api/bff/banking/sync/run", { method: "POST" });
    setBusy(false);
    if (r.ok) setMessage(t("started", { connections: r.data.connections, queued: r.data.queued }));
    else setError(r.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="bank-sync-settings">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <label className="flex items-center gap-2 text-sm">
        {t("hour")}
        <select
          className={ui.input}
          value={hour ?? 6}
          disabled={!canEdit || busy || hour === null}
          onChange={(e) => void save(Number(e.target.value))}
        >
          {Array.from({ length: 24 }, (_, h) => (
            <option key={h} value={h}>
              {`${String(h).padStart(2, "0")}:00`}
            </option>
          ))}
        </select>
      </label>
      <p className="text-xs text-muted">{t("hint")}</p>
      {canRun ? (
        <div>
          <button type="button" className={ui.secondary} onClick={runNow} disabled={busy}>
            {t("runNow")}
          </button>
        </div>
      ) : null}
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
