"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Tenant switch of the offline capture of handover protocols (rule M30-10, ADR 0016):
 *  `PATCH /tenant/settings`, field `handover_offline_enabled`, default off. Off means the CRM
 *  editor stores nothing on the device and the API refuses queued items (403 MHVP-HDOV-0003). */
export function HandoverOfflineSwitch({ initial, canUpdate }: { initial: boolean; canUpdate: boolean }) {
  const t = useTranslations("HandoverOfflineSwitch");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ handover_offline_enabled: boolean }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ handover_offline_enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.handover_offline_enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="handover-offline-switch-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="handover-offline-switch-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${enabled ? "bg-success-bg text-success-fg" : "bg-surface-2 text-muted"}`} data-testid="handover-offline-switch-status">
            {enabled ? t("status.on") : t("status.off")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("risk")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canUpdate || busy} onChange={(e) => void toggle(e.target.checked)} />
          <span>{t("label")}</span>
        </label>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
