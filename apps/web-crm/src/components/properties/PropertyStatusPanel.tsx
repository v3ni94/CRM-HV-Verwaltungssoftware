"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Status = "onboarding" | "active" | "terminated";

/** Zulässige Statuswechsel, gespiegelt aus der API (properties ALLOWED_TRANSITIONS); die API entscheidet. */
export const PROPERTY_TRANSITIONS: Record<Status, Status[]> = {
  onboarding: ["active", "terminated"],
  active: ["terminated"],
  terminated: [],
};

/** Objektstatus ändern (GAL-306, M4): Übernahme, aktiv oder beendet, mit ausdrücklicher Bestätigung.
 *  Die Beendigung der Verwaltung läuft fachlich über die Beendigung und die Verwalterwechsel-Anleitung;
 *  dieser Schritt setzt nur den Status. Aktivieren braucht mindestens eine Einheit, Beenden das Ende
 *  der Verwaltung (beides prüft die API). */
export function PropertyStatusPanel({ propertyId, status, canEdit }: { propertyId: string; status: Status; canEdit: boolean }) {
  const t = useTranslations("PropertyStatus");
  const router = useRouter();
  const options = PROPERTY_TRANSITIONS[status] ?? [];
  const [target, setTarget] = useState<Status | "">("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { busy, guard } = useBusy();

  const submit = guard(async () => {
    if (!target || !confirmed) return;
    setError(null);
    const res = await bff<unknown>(`/api/bff/properties/${propertyId}/status`, { method: "POST", body: JSON.stringify({ status: target }) });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setTarget("");
    setConfirmed(false);
    router.refresh();
  });

  if (!canEdit || options.length === 0) return null;
  return (
    <section className={ui.card} data-testid="property-status-panel">
      <h2 className="mb-2 font-medium">{t("title")}</h2>
      <p className="mb-2 text-sm text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("newStatus")}</span>
          <select
            className={ui.input}
            value={target}
            onChange={(e) => {
              setTarget(e.target.value as Status | "");
              setConfirmed(false);
            }}
          >
            <option value="">{t("choose")}</option>
            {options.map((o) => (
              <option key={o} value={o}>
                {t(`statuses.${o}`)}
              </option>
            ))}
          </select>
        </label>
        {target ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            {t(`confirm.${target}`)}
          </label>
        ) : null}
        <button type="button" className={ui.buttonSm} disabled={busy || !target || !confirmed} onClick={() => void submit()}>
          {t("apply")}
        </button>
      </div>
    </section>
  );
}
