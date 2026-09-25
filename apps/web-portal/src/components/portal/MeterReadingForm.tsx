"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Zählerstand melden (M21): geht als Vorschlag in die Prüfung der Verwaltung, keine
 *  automatische Übernahme. */
export function MeterReadingForm() {
  const t = useTranslations("Meter");
  const tPortal = useTranslations("Portal");
  const [meterId, setMeterId] = useState("");
  const [value, setValue] = useState("");
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!meterId.trim()) {
      setError(t("meterIdHint"));
      return;
    }
    if (value.trim() === "") {
      setError(t("valueRequired"));
      return;
    }
    if (!readAt) {
      setError(t("dateRequired"));
      return;
    }
    setBusy(true);
    const result = await bff<{ id: string }>("/api/bff/portal/meter-readings", {
      method: "POST",
      body: JSON.stringify({
        meter_id: meterId.trim(),
        value: value.trim().replace(",", "."),
        read_at: readAt,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setValue("");
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? <p className={ui.success}>{t("submitted")}</p> : null}
      <p className={ui.help}>{t("meterIdHint")}</p>
      <div>
        <label htmlFor="meter-id" className={ui.label}>
          {t("meterId")}
        </label>
        <input id="meter-id" className={ui.input} value={meterId} onChange={(e) => setMeterId(e.target.value)} />
      </div>
      <div>
        <label htmlFor="meter-value" className={ui.label}>
          {t("value")}
        </label>
        <input id="meter-value" inputMode="decimal" className={ui.input} value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <div>
        <label htmlFor="meter-date" className={ui.label}>
          {t("date")}
        </label>
        <input id="meter-date" type="date" className={ui.input} value={readAt} onChange={(e) => setReadAt(e.target.value)} />
      </div>
      <p className={ui.help}>{tPortal("proposalNotice")}</p>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
