"use client";
/** Umlageschlüssel und Schlüsselwerte des Objekts (C1, Handbuch Stammdaten): Schlüssel je Objekt
 *  mit Sollsumme (Betreiberwert ohne Vorgabe, zu verifizieren), Summe der Einheitenwerte zum
 *  Stichtag aus GET /properties/{id}/allocation-summary, Matrix Einheit mal Schlüssel, Erfassung
 *  neuer Werte mit Zeitraum (POST /units/{id}/allocation-values) und neuer Schlüssel
 *  (POST /properties/{id}/allocation-keys). Eine Abweichung von der Sollsumme ist eine Warnung
 *  und sperrt nichts; die Abrechnung liest die Werte erst mit den Freigaben G3 und G4. */
import type { components } from "@mhvp/api-client";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { formatQty } from "@/lib/units";

import { decimalForApi } from "./UnitsCreate";

export type AllocationSummary = components["schemas"]["AllocationSummaryOut"];
type SummaryKey = AllocationSummary["keys"][number];

const KINDS = ["static", "consumption", "fixed_amount", "fixed_share"] as const;
const CODE = /^[A-Z0-9_]{1,32}$/;
const DECIMAL = /^[0-9]{1,12}([.,][0-9]{1,8})?$/;

/** Local calendar day as ISO date (the reference date defaults to today). */
export function todayIso(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function isZero(value: string | null | undefined): boolean {
  return value != null && /^-?0+(\.0*)?$/.test(value);
}

export function AllocationKeysPanel({ propertyId, canEdit, canCreate }: { propertyId: string; canEdit: boolean; canCreate: boolean }) {
  const t = useTranslations("AllocationKeys");
  const router = useRouter();
  const [asOf, setAsOf] = useState(todayIso);
  const [data, setData] = useState<AllocationSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [expectedDraft, setExpectedDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [valueForm, setValueForm] = useState({ unit_id: "", allocation_key_id: "", value: "", valid_from: "", valid_to: "" });
  const [keyForm, setKeyForm] = useState({ code: "", name: "", unit_of_measure: "", kind: "static", expected_total: "" });

  const load = useCallback(async () => {
    const res = await bff<AllocationSummary>(`/api/bff/properties/${propertyId}/allocation-summary?as_of=${encodeURIComponent(asOf)}`);
    if (!res.ok) {
      setLoadError(res.message);
      return;
    }
    setLoadError(null);
    setData(res.data);
  }, [propertyId, asOf]);

  useEffect(() => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(asOf)) void load();
  }, [load, asOf]);

  const keys = data?.keys ?? [];
  const units = data?.units ?? [];
  const values = data?.values ?? [];
  const valueOf = (unitId: string, keyId: string) => values.find((v) => v.unit_id === unitId && v.allocation_key_id === keyId);
  const deviating = keys.filter((k) => k.difference != null && !isZero(k.difference));
  const matrixKeys = showAll ? keys : keys.filter((k) => k.expected_total != null || values.some((v) => v.allocation_key_id === k.id));

  const afterChange = async (text: string) => {
    setMessage(text);
    await load();
    router.refresh();
  };

  const saveExpected = async (key: SummaryKey) => {
    const raw = (expectedDraft[key.id] ?? "").trim();
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/properties/${propertyId}/allocation-keys/${key.id}`, {
      method: "PATCH",
      body: JSON.stringify({ expected_total: raw === "" ? null : decimalForApi(raw) }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setExpectedDraft((p) => {
      const next = { ...p };
      delete next[key.id];
      return next;
    });
    await afterChange(t("expectedSaved", { code: key.code }));
  };

  const valueValid =
    valueForm.unit_id !== "" && valueForm.allocation_key_id !== "" && DECIMAL.test(valueForm.value.trim()) && /^\d{4}-\d{2}-\d{2}$/.test(valueForm.valid_from);
  const saveValue = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      allocation_key_id: valueForm.allocation_key_id,
      value: decimalForApi(valueForm.value),
      valid_from: valueForm.valid_from,
    };
    if (valueForm.valid_to) body.valid_to = valueForm.valid_to;
    const res = await bff(`/api/bff/units/${valueForm.unit_id}/allocation-values`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setValueForm((p) => ({ ...p, value: "", valid_to: "" }));
    await afterChange(t("valueSaved"));
  };

  const keyValid = CODE.test(keyForm.code.trim()) && keyForm.name.trim().length >= 2 && keyForm.unit_of_measure.trim() !== "" && (keyForm.expected_total.trim() === "" || DECIMAL.test(keyForm.expected_total.trim()));
  const saveKey = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      code: keyForm.code.trim(),
      name: keyForm.name.trim(),
      unit_of_measure: keyForm.unit_of_measure.trim(),
      kind: keyForm.kind,
    };
    if (keyForm.expected_total.trim()) body.expected_total = decimalForApi(keyForm.expected_total);
    const res = await bff(`/api/bff/properties/${propertyId}/allocation-keys`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setKeyForm({ code: "", name: "", unit_of_measure: "", kind: "static", expected_total: "" });
    await afterChange(t("keySaved", { code: String(body.code) }));
  };

  const differenceBadge = (k: SummaryKey) => {
    if (k.expected_total == null) return <span className="text-muted">{t("noExpected")}</span>;
    if (isZero(k.difference)) return <span className={ui.badgeSuccess}>{t("matches")}</span>;
    return <span className={ui.badgeWarning}>{formatQty(k.difference)}</span>;
  };

  return (
    <section id="umlageschluessel" className={ui.card} data-testid="allocation-keys" aria-label={t("title")}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className={ui.h2}>{t("title")}</h2>
          <p className="mt-1 text-sm text-muted">{t("intro")}</p>
        </div>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("asOf")}</span>
          <input type="date" className={ui.input} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
      </div>
      {loadError ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {loadError}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={`${ui.success} mt-2`}>
          {message}
        </p>
      ) : null}

      {deviating.length ? (
        <div role="status" className={`${ui.warning} mt-3`} data-testid="allocation-warnings">
          <p className="font-medium">{t("warningTitle")}</p>
          <ul className="list-disc pl-5">
            {deviating.map((k) => (
              <li key={k.id}>
                {t("warningDeviation", {
                  code: k.code,
                  total: formatQty(k.total),
                  expected: formatQty(k.expected_total),
                  difference: formatQty(k.difference),
                  unit: k.unit_of_measure,
                })}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs">{t("warningFooter")}</p>
        </div>
      ) : null}

      {keys.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{data ? t("empty") : t("loading")}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className={ui.table} data-testid="allocation-key-table">
            <thead>
              <tr>
                <th>{t("columns.key")}</th>
                <th>{t("columns.unitOfMeasure")}</th>
                <th>{t("columns.kind")}</th>
                <th className="num">{t("columns.expectedTotal")}</th>
                <th className="num">{t("columns.total", { date: formatDate(data?.as_of) })}</th>
                <th>{t("columns.difference")}</th>
                <th className="num">{t("columns.unitsWithout")}</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>
                    <span className="font-medium">{k.code}</span> <span className="text-muted">{k.name}</span>
                  </td>
                  <td>{k.unit_of_measure}</td>
                  <td className="text-muted">{t(`kinds.${k.kind}`)}</td>
                  <td className="num">
                    {canEdit ? (
                      <span className="inline-flex items-center gap-1">
                        <input
                          aria-label={t("expectedInput", { code: k.code })}
                          className={`${ui.input} w-28 text-right`}
                          inputMode="decimal"
                          value={expectedDraft[k.id] ?? (k.expected_total == null ? "" : formatQty(k.expected_total))}
                          onChange={(e) => setExpectedDraft((p) => ({ ...p, [k.id]: e.target.value }))}
                        />
                        {expectedDraft[k.id] !== undefined ? (
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => saveExpected(k)}>
                            {t("saveExpected")}
                          </button>
                        ) : null}
                      </span>
                    ) : k.expected_total == null ? (
                      <span className="text-muted">{t("noExpected")}</span>
                    ) : (
                      formatQty(k.expected_total)
                    )}
                  </td>
                  <td className="num">{formatQty(k.total)}</td>
                  <td>{differenceBadge(k)}</td>
                  <td className="num">{k.units_without_value}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted">{t("expectedHint")}</p>
        </div>
      )}

      {units.length > 0 && keys.length > 0 ? (
        <div className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className={ui.subtitle}>{t("matrix")}</h3>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              {t("showAll")}
            </label>
          </div>
          {matrixKeys.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("noValues")}</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className={ui.table} data-testid="allocation-matrix">
                <thead>
                  <tr>
                    <th>{t("columns.unit")}</th>
                    {matrixKeys.map((k) => (
                      <th key={k.id} className="num" title={k.name}>
                        {k.code}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {units.map((u) => (
                    <tr key={u.id}>
                      <td className="font-medium tabular-nums">
                        {u.number}
                        {u.label ? <span className="font-normal text-muted"> {u.label}</span> : null}
                      </td>
                      {matrixKeys.map((k) => {
                        const v = valueOf(u.id, k.id);
                        return (
                          <td key={k.id} className="num" title={v ? `${formatDate(v.valid_from)}${v.valid_to ? ` ${t("until")} ${formatDate(v.valid_to)}` : ""}` : undefined}>
                            {v ? formatQty(v.value) : <span className="text-xs text-muted">{t("noValue")}</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                  <tr className="font-medium">
                    <td>{t("sumRow")}</td>
                    {matrixKeys.map((k) => (
                      <td key={k.id} className="num">
                        {formatQty(k.total)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {canEdit && units.length > 0 && keys.length > 0 ? (
        <div className="mt-4 border-t border-border pt-3" data-testid="allocation-value-form">
          <h3 className={ui.subtitle}>{t("addValue")}</h3>
          <div className="mt-2 grid gap-3 sm:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.unit")}</span>
              <select className={ui.input} value={valueForm.unit_id} onChange={(e) => setValueForm((p) => ({ ...p, unit_id: e.target.value }))}>
                <option value="">{t("choose")}</option>
                {units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.number}
                    {u.label ? ` ${u.label}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.key")}</span>
              <select className={ui.input} value={valueForm.allocation_key_id} onChange={(e) => setValueForm((p) => ({ ...p, allocation_key_id: e.target.value }))}>
                <option value="">{t("choose")}</option>
                {keys.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.code} {k.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.value")}</span>
              <input className={ui.input} inputMode="decimal" value={valueForm.value} onChange={(e) => setValueForm((p) => ({ ...p, value: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.validFrom")}</span>
              <input type="date" className={ui.input} value={valueForm.valid_from} onChange={(e) => setValueForm((p) => ({ ...p, valid_from: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.validTo")}</span>
              <input type="date" className={ui.input} value={valueForm.valid_to} onChange={(e) => setValueForm((p) => ({ ...p, valid_to: e.target.value }))} />
            </label>
          </div>
          <p className="mt-2 text-xs text-muted">{t("valueHint")}</p>
          <div className="mt-2">
            <button type="button" className={ui.primary} disabled={busy || !valueValid} onClick={saveValue}>
              {t("saveValue")}
            </button>
          </div>
        </div>
      ) : null}

      {canCreate ? (
        <details className="mt-4 border-t border-border pt-3" data-testid="allocation-key-form">
          <summary className="cursor-pointer text-sm font-medium">{t("addKey")}</summary>
          <div className="mt-2 grid gap-3 sm:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.code")}</span>
              <input className={ui.input} value={keyForm.code} onChange={(e) => setKeyForm((p) => ({ ...p, code: e.target.value.toUpperCase() }))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.name")}</span>
              <input className={ui.input} value={keyForm.name} onChange={(e) => setKeyForm((p) => ({ ...p, name: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.unitOfMeasure")}</span>
              <input className={ui.input} value={keyForm.unit_of_measure} onChange={(e) => setKeyForm((p) => ({ ...p, unit_of_measure: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.kind")}</span>
              <select className={ui.input} value={keyForm.kind} onChange={(e) => setKeyForm((p) => ({ ...p, kind: e.target.value }))}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`kinds.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("fields.expectedTotal")}</span>
              <input className={ui.input} inputMode="decimal" value={keyForm.expected_total} onChange={(e) => setKeyForm((p) => ({ ...p, expected_total: e.target.value }))} />
            </label>
          </div>
          <p className="mt-2 text-xs text-muted">{t("keyHint")}</p>
          <div className="mt-2">
            <button type="button" className={ui.primary} disabled={busy || !keyValid} onClick={saveKey}>
              {t("saveKey")}
            </button>
          </div>
        </details>
      ) : null}

      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
