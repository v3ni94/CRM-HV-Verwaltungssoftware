"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TrashSettingsData = { enabled: boolean; retention_days: number; proposed_days: number };

/** Papierkorb-Schalter des Mandanten (AE33, AC07-03). Standard aus: eine zulässige Löschung
 *  bleibt dann endgültig. Die Frist von 30 Tagen ist ein Vorschlag, keine Rechtsfrist; ob
 *  personenbezogene Daten so lange im Papierkorb bleiben dürfen, ist offen (AE33-01). */
export function TrashSettings({ initial, canEdit }: { initial: TrashSettingsData; canEdit: boolean }) {
  const t = useTranslations("TrashSettings");
  const [enabled, setEnabled] = useState(initial.enabled);
  const [days, setDays] = useState(String(initial.retention_days));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<TrashSettingsData>("/api/bff/documents/trash-settings", {
      method: "PUT",
      body: JSON.stringify({ enabled, retention_days: Number.parseInt(days, 10) }),
    });
    setBusy(false);
    if (result.ok) setMessage(t("saved"));
    else setError(result.message);
  }

  return (
    <section aria-labelledby="trash-settings-title" className={`${ui.card} max-w-2xl`}>
      <h2 id="trash-settings-title" className="mb-1 text-base font-semibold">
        {t("title")}
      </h2>
      <p className="mb-3 text-sm">{t("hint")}</p>
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canEdit || busy} onChange={(e) => setEnabled(e.target.checked)} />
          {t("enabled")}
        </label>
        <div className="max-w-xs">
          <label className={ui.label} htmlFor="trash-days">
            {t("days")}
          </label>
          <input
            id="trash-days"
            type="number"
            min={1}
            max={365}
            className={ui.input}
            value={days}
            disabled={!canEdit || busy}
            onChange={(e) => setDays(e.target.value)}
          />
          <p className={ui.help}>{t("daysHint", { proposed: initial.proposed_days })}</p>
        </div>
        {canEdit ? (
          <div>
            <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
              {t("save")}
            </button>
          </div>
        ) : null}
        {message ? <p role="status" className={ui.success}>{message}</p> : null}
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    </section>
  );
}
