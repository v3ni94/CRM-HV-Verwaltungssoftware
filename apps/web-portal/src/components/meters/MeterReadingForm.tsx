"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { parseGermanDecimal } from "@/lib/format";
import { ui } from "@/lib/ui";

const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/**
 * Meter reading as a proposal (PortalMeterIn: meter_id, value, read_at). The portal API has
 * no meter list endpoint, so the meter ID comes from the reading card of the management.
 */
export function MeterReadingForm() {
  const t = useTranslations("Meter");
  const today = new Date().toISOString().slice(0, 10);
  const [meterId, setMeterId] = useState("");
  const [value, setValue] = useState("");
  const [readAt, setReadAt] = useState(today);
  const [fieldErrors, setFieldErrors] = useState<{ meter?: string; value?: string; date?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setDone(false);
    const decimal = parseGermanDecimal(value);
    const errors: { meter?: string; value?: string; date?: string } = {};
    if (!UUID.test(meterId.trim())) errors.meter = t("meterRequired");
    if (decimal === null) errors.value = t("valueRequired");
    if (!readAt) errors.date = t("dateRequired");
    setFieldErrors(errors);
    if (errors.meter || errors.value || errors.date) return;
    setSubmitting(true);
    const result = await bff<{ id: string; status: string }>("/api/bff/portal/meter-readings", {
      method: "POST",
      body: JSON.stringify({ meter_id: meterId.trim(), value: decimal, read_at: readAt }),
    });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setValue("");
  }

  return (
    <form onSubmit={onSubmit} noValidate className={`${ui.card} flex max-w-xl flex-col gap-3`} aria-label={t("title")}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {t("success")}
        </p>
      ) : null}
      <div>
        <label htmlFor="meter-id" className={ui.label}>
          {t("fieldMeter")}
        </label>
        <input
          id="meter-id"
          type="text"
          className={ui.input}
          aria-invalid={!!fieldErrors.meter}
          value={meterId}
          onChange={(e) => setMeterId(e.target.value)}
        />
        <p className={ui.help}>{t("fieldMeterHelp")}</p>
        {fieldErrors.meter ? <p className={ui.error}>{fieldErrors.meter}</p> : null}
      </div>
      <div>
        <label htmlFor="meter-value" className={ui.label}>
          {t("fieldValue")}
        </label>
        <input
          id="meter-value"
          type="text"
          inputMode="decimal"
          className={ui.input}
          aria-invalid={!!fieldErrors.value}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        {fieldErrors.value ? <p className={ui.error}>{fieldErrors.value}</p> : null}
      </div>
      <div>
        <label htmlFor="meter-date" className={ui.label}>
          {t("fieldDate")}
        </label>
        <input
          id="meter-date"
          type="date"
          max={today}
          className={ui.input}
          aria-invalid={!!fieldErrors.date}
          value={readAt}
          onChange={(e) => setReadAt(e.target.value)}
        />
        {fieldErrors.date ? <p className={ui.error}>{fieldErrors.date}</p> : null}
      </div>
      <div>
        <button type="submit" className={ui.primary} disabled={submitting}>
          {submitting ? t("submitting") : t("submit")}
        </button>
      </div>
    </form>
  );
}
