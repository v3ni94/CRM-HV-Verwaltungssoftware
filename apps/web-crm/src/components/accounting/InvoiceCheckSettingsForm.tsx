"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type InvoiceCheckSettings = {
  price_tolerance_percent: string;
  quantity_tolerance_percent: string;
};

// 0 bis 100, höchstens vier Nachkommastellen (API: decimal_places=4), Komma oder Punkt.
const PERCENT = /^\d{1,3}([.,]\d{1,4})?$/;
const asNumber = (v: string) => Number(v.trim().replace(",", "."));
const isPercent = (v: string) => PERCENT.test(v.trim()) && asNumber(v) <= 100;
const toDecimal = (v: string) => v.trim().replace(",", ".");
const toInput = (v: string) => v.replace(".", ",");

/** M14-02 (T05-Rest): Toleranzen der sachlichen Rechnungsprüfung,
 *  `GET/PUT /accounting/invoice-check-settings`. Die Toleranzen steuern nur Hinweise der
 *  sachlichen Prüfung (Preis und Menge gegen Auftrag), sie geben nichts frei und buchen nichts.
 *  Speichern nur mit tenant_settings:update. Prozentwerte als Dezimalzeichenkette, kein Float
 *  im Request. */
export function InvoiceCheckSettingsForm({
  initial,
  canUpdate,
}: {
  initial: InvoiceCheckSettings;
  canUpdate: boolean;
}) {
  const t = useTranslations("InvoiceCheckSettings");
  const [price, setPrice] = useState(toInput(initial.price_tolerance_percent));
  const [quantity, setQuantity] = useState(toInput(initial.quantity_tolerance_percent));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const valid = isPercent(price) && isPercent(quantity);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<InvoiceCheckSettings>("/api/bff/accounting/invoice-check-settings", {
      method: "PUT",
      body: JSON.stringify({
        price_tolerance_percent: toDecimal(price),
        quantity_tolerance_percent: toDecimal(quantity),
      }),
    });
    setBusy(false);
    if (res.ok) {
      setPrice(toInput(res.data.price_tolerance_percent));
      setQuantity(toInput(res.data.quantity_tolerance_percent));
      setMessage(t("saved"));
    } else setError(res.message);
  }

  const field = (label: string, value: string, onChange: (v: string) => void) => (
    <label className={ui.label}>
      {label}
      <input
        className={ui.input}
        inputMode="decimal"
        value={value}
        disabled={!canUpdate}
        aria-invalid={!isPercent(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );

  return (
    <form onSubmit={save} className={ui.card} aria-labelledby="invoice-check-settings-title">
      <div className="flex flex-col gap-3">
        <h2 id="invoice-check-settings-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {field(t("price"), price, setPrice)}
          {field(t("quantity"), quantity, setQuantity)}
        </div>
        {!valid ? <p className={ui.error}>{t("invalid")}</p> : <p className={ui.help}>{t("unit")}</p>}
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {canUpdate ? (
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy || !valid}>
              {t("save")}
            </button>
          </div>
        ) : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
