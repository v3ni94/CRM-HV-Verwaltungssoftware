"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** T01-01: retention of tenant export archives in days (`PATCH /tenant/settings`,
 *  `export_retention_days`, 1 to 3650). Empty means no automatic deletion. The daily job deletes
 *  expired archives from the object store and marks the export as expired; every change is
 *  written to the event log as `tenant_settings.updated`. */
export function ExportRetentionSetting({
  initial,
  canUpdate,
}: {
  initial: number | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("ExportRetention");
  const [days, setDays] = useState(initial === null ? "" : String(initial));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const value = days.trim();
    const n = Number(value);
    if (value !== "" && (!/^\d+$/.test(value) || n < 1 || n > 3650)) {
      setError(t("invalid"));
      setMessage(null);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ export_retention_days: number | null }>(
      "/api/bff/tenant/settings",
      {
        method: "PATCH",
        body: JSON.stringify(
          value === ""
            ? { clear_export_retention_days: true }
            : { export_retention_days: n },
        ),
      },
    );
    setBusy(false);
    if (res.ok) {
      const saved = res.data.export_retention_days;
      setDays(saved === null ? "" : String(saved));
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="export-retention-title">
      <div className="flex flex-col gap-3">
        <h2 id="export-retention-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("label")}</span>
            <input
              type="number"
              min={1}
              max={3650}
              className={ui.input}
              value={days}
              disabled={!canUpdate || busy}
              onChange={(e) => setDays(e.target.value)}
              data-testid="export-retention-days"
            />
          </label>
          <button
            type="button"
            className={ui.secondary}
            disabled={!canUpdate || busy}
            onClick={() => void save()}
          >
            {t("save")}
          </button>
        </div>
        <p className={ui.help}>{t("hint")}</p>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? (
          <span className="text-xs text-success-fg">{message}</span>
        ) : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
