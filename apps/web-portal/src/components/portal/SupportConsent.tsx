"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Consent = { active: boolean; expires_at: string | null };

/** Einwilligung in die lesende Support-Sicht (SA-02): zeitlich begrenzt, jederzeit widerrufbar,
 *  jeder Aufruf der Verwaltung wird protokolliert. Ohne Einwilligung hat die Verwaltung keinen
 *  Einblick in das Konto. */
export function SupportConsent({ initial }: { initial: Consent }) {
  const t = useTranslations("SupportConsent");
  const format = useFormatter();
  const [consent, setConsent] = useState<Consent>(initial);
  const [hours, setHours] = useState("24");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function grant(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const result = await bff<Consent>("/api/bff/portal/support-consent", {
      method: "POST",
      body: JSON.stringify({ hours: Number(hours) }),
    });
    setBusy(false);
    if (!result.ok) setError(result.message);
    else setConsent(result.data);
  }

  async function revoke() {
    setError(null);
    setBusy(true);
    const result = await bff<null>("/api/bff/portal/support-consent", { method: "DELETE" });
    setBusy(false);
    if (!result.ok) setError(result.message);
    else setConsent({ active: false, expires_at: null });
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="support-consent-title">
      <h2 id="support-consent-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {consent.active && consent.expires_at ? (
        <div className="flex flex-col gap-2">
          <p role="status" className={ui.success}>
            {t("active", {
              until: format.dateTime(new Date(consent.expires_at), {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              }),
            })}
          </p>
          <button type="button" className={ui.button} disabled={busy} onClick={revoke}>
            {t("revoke")}
          </button>
        </div>
      ) : (
        <form onSubmit={grant} className="flex flex-col gap-2" aria-label={t("title")}>
          <label htmlFor="support-hours" className={ui.label}>
            {t("hours")}
          </label>
          <select id="support-hours" className={ui.input} value={hours} onChange={(e) => setHours(e.target.value)}>
            {["1", "4", "24", "72"].map((h) => (
              <option key={h} value={h}>
                {t("hoursOption", { hours: h })}
              </option>
            ))}
          </select>
          <button type="submit" className={ui.button} disabled={busy}>
            {t("grant")}
          </button>
        </form>
      )}
    </section>
  );
}
