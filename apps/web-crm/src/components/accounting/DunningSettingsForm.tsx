"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type DunningLevel = {
  level: number;
  min_days_overdue: number;
  text: string;
  fee_amount: string | null;
};

export type DunningSettings = {
  levels: DunningLevel[];
  threshold_amount: string;
  fee_from_level: number | null;
  interest_enabled: boolean;
  interest_base_rate: string | null;
  interest_spread: string | null;
  status: string;
};

const EMPTY_LEVEL: DunningLevel = { level: 1, min_days_overdue: 7, text: "", fee_amount: null };

/** Mahnstufen, Gebühr je Stufe (nur mit hinterlegtem Betrag) und gesetzlicher Verzugszins
 * (Basiszinssatz plus Aufschlag, Betreiberentscheidung 25.09.2026, V7 teilweise entschieden,
 * docs/rules/M16-01.md). Kein Wert wird hier je vorbelegt, "Vorschlagswerte laden" lässt
 * Gebühren und Basiszinssatz ausdrücklich leer. */
export function DunningSettingsForm({
  propertyId,
  initial,
  canUpdate,
}: {
  propertyId?: string;
  initial: DunningSettings;
  canUpdate: boolean;
}) {
  const t = useTranslations("Dunning");
  const [levels, setLevels] = useState<DunningLevel[]>(
    initial.levels.length ? initial.levels : [EMPTY_LEVEL],
  );
  const [threshold, setThreshold] = useState(initial.threshold_amount);
  const [feeFromLevel, setFeeFromLevel] = useState(initial.fee_from_level?.toString() ?? "");
  const [interestEnabled, setInterestEnabled] = useState(initial.interest_enabled);
  const [baseRate, setBaseRate] = useState(initial.interest_base_rate ?? "");
  const [spread, setSpread] = useState(initial.interest_spread ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateLevel(index: number, patch: Partial<DunningLevel>) {
    setLevels((prev) => prev.map((lv, i) => (i === index ? { ...lv, ...patch } : lv)));
  }

  function addLevel() {
    const next = (levels.at(-1)?.level ?? 0) + 1;
    setLevels((prev) => [...prev, { ...EMPTY_LEVEL, level: next }]);
  }

  function removeLevel(index: number) {
    setLevels((prev) => prev.filter((_, i) => i !== index));
  }

  async function loadPresets() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<DunningSettings>("/api/bff/accounting/dunning-settings/presets", {
      method: "POST",
      body: JSON.stringify({ property_id: propertyId ?? null }),
    });
    setBusy(false);
    if (result.ok) {
      setLevels(result.data.levels);
      setThreshold(result.data.threshold_amount ?? threshold);
      setFeeFromLevel(result.data.fee_from_level?.toString() ?? "");
      setInterestEnabled(false);
      setBaseRate("");
      setSpread(result.data.interest_spread ?? "");
      setMessage(t("presetsLoaded"));
    } else {
      setError(result.message);
    }
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<DunningSettings>("/api/bff/accounting/dunning-settings", {
      method: "PUT",
      body: JSON.stringify({
        property_id: propertyId ?? null,
        levels: levels.map((lv) => ({
          level: lv.level,
          min_days_overdue: lv.min_days_overdue,
          text: lv.text,
          fee_amount: lv.fee_amount || null,
        })),
        threshold_amount: threshold || "0",
        fee_from_level: feeFromLevel ? Number(feeFromLevel) : null,
        interest_enabled: interestEnabled,
        interest_base_rate: baseRate || null,
        interest_spread: spread || null,
      }),
    });
    setBusy(false);
    if (result.ok) {
      setMessage(t("saved"));
    } else {
      setError(result.message);
    }
  }

  const canEnableInterest = baseRate.trim().length > 0;

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("settingsTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("settingsNotice")}</p>
      <p className={`${ui.notice} mt-2`}>{t("feesLocked")}</p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.secondary} onClick={loadPresets} disabled={busy || !canUpdate}>
          {t("loadPresets")}
        </button>
        <label className="flex items-center gap-2 text-sm">
          <span className={ui.label}>{t("feeFromLevel")}</span>
          <input
            type="number"
            min={1}
            className={`${ui.input} w-24`}
            value={feeFromLevel}
            onChange={(e) => setFeeFromLevel(e.target.value)}
            disabled={!canUpdate}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <span className={ui.label}>{t("thresholdAmount")}</span>
          <input
            className={`${ui.input} w-28`}
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            disabled={!canUpdate}
          />
        </label>
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("levelNo")}</th>
              <th>{t("minDays")}</th>
              <th>{t("levelText")}</th>
              <th>{t("feeAmount")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {levels.map((lv, i) => (
              <tr key={i}>
                <td>
                  <input
                    type="number"
                    min={1}
                    className={`${ui.input} w-16`}
                    value={lv.level}
                    onChange={(e) => updateLevel(i, { level: Number(e.target.value) })}
                    disabled={!canUpdate}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    className={`${ui.input} w-20`}
                    value={lv.min_days_overdue}
                    onChange={(e) => updateLevel(i, { min_days_overdue: Number(e.target.value) })}
                    disabled={!canUpdate}
                  />
                </td>
                <td>
                  <input
                    className={ui.input}
                    value={lv.text}
                    onChange={(e) => updateLevel(i, { text: e.target.value })}
                    disabled={!canUpdate}
                  />
                </td>
                <td>
                  <input
                    className={`${ui.input} w-28`}
                    placeholder="—"
                    value={lv.fee_amount ?? ""}
                    onChange={(e) => updateLevel(i, { fee_amount: e.target.value || null })}
                    disabled={!canUpdate}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() => removeLevel(i)}
                    disabled={!canUpdate || levels.length <= 1}
                  >
                    {t("removeLevel")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className={`${ui.button} mt-2`} onClick={addLevel} disabled={!canUpdate}>
        {t("addLevel")}
      </button>

      <h3 className={`${ui.h2} mt-6 text-base`}>{t("interestSection")}</h3>
      <div className="mt-2 flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm">
          <span className={ui.label}>{t("interestBaseRate")}</span>
          <input
            className={`${ui.input} w-32`}
            value={baseRate}
            onChange={(e) => setBaseRate(e.target.value)}
            disabled={!canUpdate}
          />
        </label>
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className={ui.label}>{t("interestSpread")}</span>
            <input
              className={`${ui.input} w-24`}
              value={spread}
              onChange={(e) => setSpread(e.target.value)}
              disabled={!canUpdate}
            />
          </label>
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => setSpread("5")}
            disabled={!canUpdate}
          >
            {t("interestSpreadPresetConsumer")}
          </button>
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => setSpread("9")}
            disabled={!canUpdate}
          >
            {t("interestSpreadPresetBusiness")}
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={interestEnabled}
            onChange={(e) => setInterestEnabled(e.target.checked)}
            disabled={!canUpdate || !canEnableInterest}
          />
          <span>{t("interestEnabled")}</span>
        </label>
        <p className={ui.help}>{t("interestEnabledHint")}</p>
      </div>

      <div className="mt-4">
        <button type="button" className={ui.primary} onClick={save} disabled={busy || !canUpdate}>
          {t("save")}
        </button>
      </div>
      {message ? <p className={`${ui.success} mt-2`}>{message}</p> : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
