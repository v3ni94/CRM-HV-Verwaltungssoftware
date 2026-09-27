"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { fieldPath } from "@/lib/problem";
import { ui } from "@/lib/ui";

/** API-Feldnamen des Vorschlags und die zugehörigen Element-IDs des Formulars. */
const FIELD_IDS: Record<string, string> = {
  meter_id: "meter-id",
  value: "meter-value",
  read_at: "meter-date",
};

/** Zählerstand melden (M21): geht als Vorschlag in die Prüfung der Verwaltung, keine
 *  automatische Übernahme. */
export function MeterReadingForm() {
  const t = useTranslations("Meter");
  const tPortal = useTranslations("Portal");
  const [meterId, setMeterId] = useState("");
  const [value, setValue] = useState("");
  const [readAt, setReadAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  function fieldProps(name: keyof typeof FIELD_IDS) {
    const message = fieldErrors[name];
    return {
      "aria-invalid": message ? true : undefined,
      "aria-describedby": message ? `${FIELD_IDS[name]}-error` : undefined,
    };
  }

  function fieldErrorText(name: keyof typeof FIELD_IDS) {
    const message = fieldErrors[name];
    if (!message) return null;
    return (
      <p id={`${FIELD_IDS[name]}-error`} className={ui.error}>
        {message}
      </p>
    );
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setDone(false);
    // Alle Pflichtfeldfehler auf einmal anzeigen, nicht nur den ersten.
    const missing: Record<string, string> = {};
    if (!meterId.trim()) missing.meter_id = t("meterIdRequired");
    if (value.trim() === "") missing.value = t("valueRequired");
    if (!readAt) missing.read_at = t("dateRequired");
    setFieldErrors(missing);
    if (Object.keys(missing).length > 0) return;
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
      // 422: Feldfehler der API (z. B. ["body", "value"]) den Eingabefeldern zuordnen.
      const errors: Record<string, string> = {};
      for (const fieldError of result.status === 422 ? (result.problem?.errors ?? []) : []) {
        const name = fieldPath(fieldError.location)?.split(".").pop();
        if (name && name in FIELD_IDS) errors[name] = fieldError.message;
      }
      setFieldErrors(errors);
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
        <input
          id="meter-id"
          autoComplete="off"
          className={ui.input}
          value={meterId}
          onChange={(e) => setMeterId(e.target.value)}
          {...fieldProps("meter_id")}
        />
        {fieldErrorText("meter_id")}
      </div>
      <div>
        <label htmlFor="meter-value" className={ui.label}>
          {t("value")}
        </label>
        <input
          id="meter-value"
          inputMode="decimal"
          autoComplete="off"
          className={ui.input}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          {...fieldProps("value")}
        />
        {fieldErrorText("value")}
      </div>
      <div>
        <label htmlFor="meter-date" className={ui.label}>
          {t("date")}
        </label>
        <input
          id="meter-date"
          type="date"
          autoComplete="off"
          className={ui.input}
          value={readAt}
          onChange={(e) => setReadAt(e.target.value)}
          {...fieldProps("read_at")}
        />
        {fieldErrorText("read_at")}
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
