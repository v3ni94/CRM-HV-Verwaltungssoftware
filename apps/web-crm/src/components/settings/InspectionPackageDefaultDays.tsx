"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** P08-04, M25-07 (PÜ13): default period of an inspection package in days. Empty means no
 *  expiry. Applies only when a package is created without its own period
 *  (`PATCH /tenant/settings`, 1 to 365; `clear_inspection_package_default_days` empties it). */
export function InspectionPackageDefaultDays({ initial, canUpdate }: { initial: number | null; canUpdate: boolean }) {
  const t = useTranslations("InspectionPackageDefaultDays");
  const [days, setDays] = useState(initial === null ? "" : String(initial));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const value = days.trim();
    const n = Number(value);
    if (value !== "" && (!/^\d+$/.test(value) || n < 1 || n > 365)) {
      setError(t("invalid"));
      setMessage(null);
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    const body = value === "" ? { clear_inspection_package_default_days: true } : { inspection_package_default_days: n };
    const res = await bff<{ inspection_package_default_days: number | null }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (res.ok) {
      const next = res.data.inspection_package_default_days;
      setDays(next === null || next === undefined ? "" : String(next));
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="inspection-package-days-title">
      <div className="flex flex-col gap-3">
        <h2 id="inspection-package-days-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("description")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("label")}</span>
            <input
              type="number"
              min={1}
              max={365}
              className={ui.input}
              value={days}
              disabled={!canUpdate || busy}
              onChange={(e) => setDays(e.target.value)}
              data-testid="inspection-package-default-days"
            />
          </label>
          <button type="button" className={ui.secondary} disabled={!canUpdate || busy} onClick={() => void save()}>
            {t("save")}
          </button>
        </div>
        <p className={ui.help}>{t("hint")}</p>
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
