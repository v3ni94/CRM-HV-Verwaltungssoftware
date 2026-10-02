"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type HeatingRowInput = {
  user_number: string;
  heating_base: string;
  heating_consumption: string;
  hot_water_base: string;
  hot_water_consumption: string;
};
const AMOUNT = /^\d+([.,]\d{1,2})?$/;
const FIELDS = ["heating_base", "heating_consumption", "hot_water_base", "hot_water_consumption"] as const;
const LABEL: Record<(typeof FIELDS)[number], string> = {
  heating_base: "heatingBase",
  heating_consumption: "heatingConsumption",
  hot_water_base: "hotWaterBase",
  hot_water_consumption: "hotWaterConsumption",
};
const blank = (): HeatingRowInput => ({ user_number: "", heating_base: "", heating_consumption: "", hot_water_base: "", hot_water_consumption: "" });

/** Kostenzeilen des Messdienstimports manuell erfassen (GAI-419): `PUT /billing/heating-cost-imports/{id}/rows`
 *  ersetzt die Zeilen. Beträge als Text, keine Gleitkommarechnung. Nur ein Importentwurf, keine Abrechnung. */
export function HeatingImportRowsForm({ importId, initial = [], editable, onSaved }: { importId: string; initial?: HeatingRowInput[]; editable: boolean; onSaved?: (data: unknown) => void }) {
  const t = useTranslations("Aj17.heatingRows");
  const [rows, setRows] = useState<HeatingRowInput[]>(initial.length > 0 ? initial : [blank()]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  if (!editable) return null;
  const set = (i: number, key: keyof HeatingRowInput, value: string) => setRows((r) => r.map((x, j) => (j === i ? { ...x, [key]: value } : x)));
  const save = async () => {
    const valid = rows.every((r) => r.user_number.trim() && FIELDS.every((f) => AMOUNT.test(r[f].trim())));
    if (!valid) {
      setMessage({ ok: false, text: t("invalid") });
      return;
    }
    const payload = rows.map((r) => ({
      user_number: r.user_number.trim(),
      ...Object.fromEntries(FIELDS.map((f) => [f, r[f].trim().replace(",", ".")])),
    }));
    setBusy(true);
    setMessage(null);
    const res = await bff<unknown>(`/api/bff/billing/heating-cost-imports/${importId}/rows`, { method: "PUT", body: JSON.stringify({ rows: payload }) });
    setBusy(false);
    if (res.ok) {
      setMessage({ ok: true, text: t("saved", { count: payload.length }) });
      onSaved?.(res.data);
    } else setMessage({ ok: false, text: res.message });
  };
  return (
    <fieldset className="flex flex-col gap-2" data-testid="heating-rows-form">
      <legend className={ui.label}>{t("title")}</legend>
      <p className={ui.help}>{t("hint")}</p>
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("userNumber")}</span>
            <input className={ui.input} value={r.user_number} onChange={(e) => set(i, "user_number", e.target.value)} aria-label={`${t("userNumber")} ${i + 1}`} />
          </label>
          {FIELDS.map((f) => (
            <label key={f} className="flex flex-col gap-1">
              <span className={ui.label}>{t(LABEL[f])}</span>
              <input className={ui.input} inputMode="decimal" value={r[f]} onChange={(e) => set(i, f, e.target.value)} aria-label={`${t(LABEL[f])} ${i + 1}`} />
            </label>
          ))}
          <button type="button" className={ui.buttonSm} onClick={() => setRows((x) => (x.length > 1 ? x.filter((_, j) => j !== i) : x))}>
            {t("removeRow")}
          </button>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.secondary} onClick={() => setRows((x) => [...x, blank()])}>
          {t("addRow")}
        </button>
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
      </div>
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
    </fieldset>
  );
}
