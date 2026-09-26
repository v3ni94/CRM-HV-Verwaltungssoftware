"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type DunningLevel = {
  level: number;
  min_days_overdue: number;
  text: string;
  fee_amount: string | null;
  payment_days?: number | null;
  letter_text?: string | null;
};

export type DunningSource = "objekt" | "mandant";

export type DunningOwnRow = {
  id: string;
  levels: DunningLevel[] | null;
  threshold_amount: string | null;
  fee_from_level: number | null;
  interest_enabled: boolean | null;
  interest_base_rate: string | null;
  interest_spread: string | null;
};

/** Wirksame Werte (nach Vererbung); `sources` nennt je Feld die Quelle, `own` ist die
 * gespeicherte Zeile des Geltungsbereichs (bei Objekten null, solange nichts überschrieben ist). */
export type DunningSettings = {
  levels: DunningLevel[];
  threshold_amount: string;
  fee_from_level: number | null;
  interest_enabled: boolean;
  interest_base_rate: string | null;
  interest_spread: string | null;
  status: string;
  sources?: Partial<Record<string, DunningSource>>;
  own?: DunningOwnRow | null;
  tenant_default_exists?: boolean;
};

/** Antwort von `POST /accounting/dunning-settings/letter-preview` (A33): Text der Stufe mit
 * Beispielposten; Gebühr und Frist nur aus den übergebenen Werten, keine Bankverbindung. */
export type LetterTextPreview = {
  level: number;
  paragraphs: string[];
  table: { header: string[]; rows: string[][] };
  standard_request: string;
  placeholders: Record<string, string>;
  hinweis: string;
};

const PLACEHOLDERS = ["{frist}", "{bankverbindung}", "{gesamtbetrag}", "{forderungsinhaber}", "{objekt}", "{stufe}"];

const EMPTY_LEVEL: DunningLevel = {
  level: 1,
  min_days_overdue: 7,
  text: "",
  fee_amount: null,
  payment_days: null,
  letter_text: null,
};

/** Mahnstufen, Gebühr je Stufe (nur mit hinterlegtem Betrag) und gesetzlicher Verzugszins
 * (Basiszinssatz plus Aufschlag, Betreiberentscheidung 25.09.2026, V7 teilweise entschieden,
 * docs/rules/M16-01.md). Kein Wert wird hier je vorbelegt, "Vorschlagswerte laden" lässt
 * Gebühren und Basiszinssatz ausdrücklich leer.
 *
 * Mit `propertyId` bearbeitet das Formular die Objektüberschreibung (docs/rules/M16-02.md):
 * je Abschnitt entscheidet ein Häkchen "vom Mandanten übernehmen", ob der Wert leer bleibt
 * (erben) oder ein eigener Wert gespeichert wird. */
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
  const router = useRouter();
  const isOverride = Boolean(propertyId);
  const own = initial.own ?? null;
  const [levels, setLevels] = useState<DunningLevel[]>(
    initial.levels.length ? initial.levels : [EMPTY_LEVEL],
  );
  const [threshold, setThreshold] = useState(initial.threshold_amount);
  const [feeFromLevel, setFeeFromLevel] = useState(initial.fee_from_level?.toString() ?? "");
  const [interestEnabled, setInterestEnabled] = useState(initial.interest_enabled);
  const [baseRate, setBaseRate] = useState(initial.interest_base_rate ?? "");
  const [spread, setSpread] = useState(initial.interest_spread ?? "");
  // Objektmodus: ein Abschnitt erbt, solange die gespeicherte Objektzeile dort NULL hat.
  const [inheritLadder, setInheritLadder] = useState(isOverride && (own?.levels ?? null) === null);
  const [inheritThreshold, setInheritThreshold] = useState(
    isOverride && (own?.threshold_amount ?? null) === null,
  );
  const [inheritFeeFromLevel, setInheritFeeFromLevel] = useState(
    isOverride && (own?.fee_from_level ?? null) === null,
  );
  const [inheritInterest, setInheritInterest] = useState(
    isOverride &&
      (own?.interest_enabled ?? null) === null &&
      (own?.interest_base_rate ?? null) === null &&
      (own?.interest_spread ?? null) === null,
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<LetterTextPreview | null>(null);

  const tenantDefaultMissing = isOverride && initial.tenant_default_exists === false;
  const editable = canUpdate && !tenantDefaultMissing;

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

  function source(field: string): string | null {
    if (!isOverride) return null;
    const src = initial.sources?.[field];
    return src ? t(src === "objekt" ? "sourceObjekt" : "sourceMandant") : null;
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
      if (isOverride) {
        setInheritLadder(false);
        setInheritFeeFromLevel(false);
      }
      setMessage(t("presetsLoaded"));
    } else {
      setError(result.message);
    }
  }

  function ladderPayload() {
    return levels.map((lv) => ({
      level: lv.level,
      min_days_overdue: lv.min_days_overdue,
      text: lv.text,
      fee_amount: lv.fee_amount || null,
      payment_days:
        lv.payment_days === null || lv.payment_days === undefined || Number.isNaN(lv.payment_days)
          ? null
          : lv.payment_days,
      letter_text: lv.letter_text?.trim() ? lv.letter_text : null,
    }));
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const body = isOverride
      ? {
          property_id: propertyId,
          levels: inheritLadder ? null : ladderPayload(),
          threshold_amount: inheritThreshold ? null : threshold || "0",
          fee_from_level: inheritFeeFromLevel ? null : feeFromLevel ? Number(feeFromLevel) : null,
          interest_enabled: inheritInterest ? null : interestEnabled,
          interest_base_rate: inheritInterest ? null : baseRate || null,
          interest_spread: inheritInterest ? null : spread || null,
        }
      : {
          property_id: null,
          levels: ladderPayload(),
          threshold_amount: threshold || "0",
          fee_from_level: feeFromLevel ? Number(feeFromLevel) : null,
          interest_enabled: interestEnabled,
          interest_base_rate: baseRate || null,
          interest_spread: spread || null,
        };
    const result = await bff<DunningSettings>("/api/bff/accounting/dunning-settings", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (result.ok) {
      setMessage(t("saved"));
      router.refresh();
    } else {
      setError(result.message);
    }
  }

  async function previewLevel(lv: DunningLevel) {
    setBusy(true);
    setError(null);
    const result = await bff<LetterTextPreview>("/api/bff/accounting/dunning-settings/letter-preview", {
      method: "POST",
      body: JSON.stringify({
        level: lv.level,
        text: lv.text || null,
        letter_text: lv.letter_text?.trim() ? lv.letter_text : null,
        fee_amount: lv.fee_amount || null,
        payment_days:
          lv.payment_days === null || lv.payment_days === undefined || Number.isNaN(lv.payment_days)
            ? null
            : lv.payment_days,
      }),
    });
    setBusy(false);
    if (result.ok) setPreview(result.data);
    else setError(result.message);
  }

  async function removeOverride() {
    if (!propertyId || !window.confirm(t("confirmRemoveOverride"))) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<null>(
      `/api/bff/accounting/dunning-settings?property_id=${encodeURIComponent(propertyId)}`,
      { method: "DELETE" },
    );
    setBusy(false);
    if (result.ok) {
      setMessage(t("overrideRemoved"));
      router.refresh();
    } else {
      setError(result.message);
    }
  }

  const canEnableInterest = baseRate.trim().length > 0;
  const ladderDisabled = !editable || inheritLadder;
  const interestDisabled = !editable || inheritInterest;

  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("settingsTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("settingsNotice")}</p>
      <p className={`${ui.notice} mt-2`}>{t("feesLocked")}</p>
      {isOverride ? <p className={`${ui.help} mt-2`}>{t("inheritanceNotice")}</p> : null}
      {tenantDefaultMissing ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {t("tenantDefaultMissing")}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.secondary} onClick={loadPresets} disabled={busy || !editable}>
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
            disabled={!editable || inheritFeeFromLevel}
          />
          {source("fee_from_level") ? <span className={ui.badge}>{source("fee_from_level")}</span> : null}
        </label>
        {isOverride ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={inheritFeeFromLevel}
              onChange={(e) => setInheritFeeFromLevel(e.target.checked)}
              disabled={!editable}
            />
            <span>{t("inheritFeeFromLevel")}</span>
          </label>
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <span className={ui.label}>{t("thresholdAmount")}</span>
          <input
            className={`${ui.input} w-28`}
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
            disabled={!editable || inheritThreshold}
          />
          {source("threshold_amount") ? <span className={ui.badge}>{source("threshold_amount")}</span> : null}
        </label>
        {isOverride ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={inheritThreshold}
              onChange={(e) => setInheritThreshold(e.target.checked)}
              disabled={!editable}
            />
            <span>{t("inheritThreshold")}</span>
          </label>
        ) : null}
      </div>

      {isOverride ? (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={inheritLadder}
            onChange={(e) => setInheritLadder(e.target.checked)}
            disabled={!editable}
          />
          <span>{t("inheritLadder")}</span>
          {source("levels") ? <span className={ui.badge}>{source("levels")}</span> : null}
        </label>
      ) : null}
      <div className="mt-3 overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("levelNo")}</th>
              <th>{t("minDays")}</th>
              <th>{t("levelText")}</th>
              <th>{t("feeAmount")}</th>
              <th>{t("paymentDays")}</th>
              <th>{t("letterText")}</th>
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
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    className={`${ui.input} w-20`}
                    value={lv.min_days_overdue}
                    onChange={(e) => updateLevel(i, { min_days_overdue: Number(e.target.value) })}
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <input
                    className={ui.input}
                    value={lv.text}
                    onChange={(e) => updateLevel(i, { text: e.target.value })}
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <input
                    className={`${ui.input} w-28`}
                    value={lv.fee_amount ?? ""}
                    onChange={(e) => updateLevel(i, { fee_amount: e.target.value || null })}
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    className={`${ui.input} w-20`}
                    value={lv.payment_days ?? ""}
                    onChange={(e) =>
                      updateLevel(i, { payment_days: e.target.value === "" ? null : Number(e.target.value) })
                    }
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <textarea
                    className={`${ui.input} min-w-[16rem]`}
                    rows={2}
                    value={lv.letter_text ?? ""}
                    onChange={(e) => updateLevel(i, { letter_text: e.target.value || null })}
                    disabled={ladderDisabled}
                  />
                </td>
                <td>
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      className={ui.buttonSm}
                      onClick={() => previewLevel(lv)}
                      disabled={busy}
                      aria-label={t("letterPreviewTitle", { level: lv.level })}
                    >
                      {t("letterPreview")}
                    </button>
                    <button
                      type="button"
                      className={ui.buttonSm}
                      onClick={() => removeLevel(i)}
                      disabled={ladderDisabled || levels.length <= 1}
                    >
                      {t("removeLevel")}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={`${ui.help} mt-2`}>
        {t("letterTextHint", {
          placeholders: PLACEHOLDERS.join(", "),
          frist: "{frist}",
          bankverbindung: "{bankverbindung}",
        })}
      </p>
      <button type="button" className={`${ui.button} mt-2`} onClick={addLevel} disabled={ladderDisabled}>
        {t("addLevel")}
      </button>
      {preview ? (
        <section className="mt-4 rounded border border-border p-3" aria-label={t("letterPreviewTitle", { level: preview.level })}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold">{t("letterPreviewTitle", { level: preview.level })}</h3>
            <span className={ui.badge}>{preview.hinweis}</span>
          </div>
          <div className="mt-2 flex flex-col gap-2 text-sm">
            {preview.paragraphs.slice(0, 2).map((paragraph, i) => (
              <p key={`a${i}`}>{paragraph}</p>
            ))}
            <table className={ui.table}>
              <caption className="text-left text-xs text-muted">{t("letterPreviewTable")}</caption>
              <thead>
                <tr>
                  {preview.table.header.map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.table.rows.map((row, i) => (
                  <tr key={i} className={i === preview.table.rows.length - 1 ? "font-semibold" : undefined}>
                    {row.map((cell, j) => (
                      <td key={j} className={j === 2 ? "text-right" : undefined}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {preview.paragraphs.slice(2).map((paragraph, i) => (
              <p key={`b${i}`}>{paragraph}</p>
            ))}
          </div>
          <button type="button" className={`${ui.buttonSm} mt-2`} onClick={() => setPreview(null)}>
            {t("letterPreviewClose")}
          </button>
        </section>
      ) : null}

      <h3 className={`${ui.h2} mt-6 text-base`}>
        {t("interestSection")}
        {source("interest_base_rate") ? <span className={`${ui.badge} ml-2`}>{source("interest_base_rate")}</span> : null}
      </h3>
      {isOverride ? (
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={inheritInterest}
            onChange={(e) => setInheritInterest(e.target.checked)}
            disabled={!editable}
          />
          <span>{t("inheritInterest")}</span>
        </label>
      ) : null}
      <div className="mt-2 flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm">
          <span className={ui.label}>{t("interestBaseRate")}</span>
          <input
            className={`${ui.input} w-32`}
            value={baseRate}
            onChange={(e) => setBaseRate(e.target.value)}
            disabled={interestDisabled}
          />
        </label>
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <span className={ui.label}>{t("interestSpread")}</span>
            <input
              className={`${ui.input} w-24`}
              value={spread}
              onChange={(e) => setSpread(e.target.value)}
              disabled={interestDisabled}
            />
          </label>
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => setSpread("5")}
            disabled={interestDisabled}
          >
            {t("interestSpreadPresetConsumer")}
          </button>
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => setSpread("9")}
            disabled={interestDisabled}
          >
            {t("interestSpreadPresetBusiness")}
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={interestEnabled}
            onChange={(e) => setInterestEnabled(e.target.checked)}
            disabled={interestDisabled || !canEnableInterest}
          />
          <span>{t("interestEnabled")}</span>
        </label>
        <p className={ui.help}>{t("interestEnabledHint")}</p>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" className={ui.primary} onClick={save} disabled={busy || !editable}>
          {t("save")}
        </button>
        {isOverride && own ? (
          <button type="button" className={ui.danger} onClick={removeOverride} disabled={busy || !editable}>
            {t("removeOverride")}
          </button>
        ) : null}
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
