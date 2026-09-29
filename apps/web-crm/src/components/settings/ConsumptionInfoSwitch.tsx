"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ConsumptionInfoSettings = {
  consumption_info_enabled: boolean;
  consumption_info_notifications_enabled: boolean;
  consumption_info_template_verified: boolean;
};

const FIELDS: { key: keyof ConsumptionInfoSettings; label: "job" | "notifications" | "verified" }[] = [
  { key: "consumption_info_enabled", label: "job" },
  { key: "consumption_info_notifications_enabled", label: "notifications" },
  { key: "consumption_info_template_verified", label: "verified" },
];

/** Mandantenschalter der Verbrauchsinformation (Regel H03, `PATCH /tenant/settings`): Monatsjob
 *  (Standard aus), Portalbenachrichtigung (Standard aus) und die Bestätigung des Betreibers, dass
 *  die Vorlage geprüft ist. Ohne diese Bestätigung sehen Mieter im Portal nichts. */
export function ConsumptionInfoSwitch({ initial, canUpdate }: { initial: ConsumptionInfoSettings; canUpdate: boolean }) {
  const t = useTranslations("ConsumptionInfoSwitch");
  const [state, setState] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(key: keyof ConsumptionInfoSettings, next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<ConsumptionInfoSettings>("/api/bff/tenant/settings", { method: "PATCH", body: JSON.stringify({ [key]: next }) });
    setBusy(false);
    if (res.ok) {
      setState((s) => ({ ...s, [key]: res.data[key] }));
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="consumption-info-switch-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="consumption-info-switch-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span className={state.consumption_info_enabled ? ui.badgeSuccess : ui.badge} data-testid="consumption-info-switch-status">
            {state.consumption_info_enabled ? t("status.on") : t("status.off")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("risk")}</p>
        {FIELDS.map((f) => (
          <label key={f.key} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={state[f.key]} disabled={!canUpdate || busy} onChange={(e) => void toggle(f.key, e.target.checked)} data-testid={`consumption-info-${f.label}`} />
            <span>{t(`labels.${f.label}`)}</span>
          </label>
        ))}
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
