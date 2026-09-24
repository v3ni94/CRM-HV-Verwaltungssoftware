"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Property = { id: string; number: string; name: string };
type Unit = { id: string; number: string; label: string | null };

type Match = {
  unit_id: string | null;
  property_id: string | null;
  unit_number: string | null;
  property_number: string | null;
  basis: string | null;
};

export type FlowImportRow = {
  index: number;
  external_uuid: string | null;
  external_ref: string | null;
  title: string | null;
  kind: "rental" | "sale";
  object_type: string;
  status: string;
  listing_fields: { price?: string | null; [key: string]: unknown };
  match: Match;
  problems: string[];
  applied?: boolean;
  outcome?: string;
  listing_id?: string;
};

export type FlowImportRun = {
  id: string;
  filename: string;
  status: string;
  row_count: number;
  created_count: number;
  skipped_count: number;
  rows: FlowImportRow[];
  applied_at: string | null;
};

type RowDecision = { action: "create" | "skip"; unitId: string | null; propertyId: string | null };

/** FLOW SQL dump import (M28 stage 4, docs/rules/M28-01.md): upload the exported database
 *  dump, review the preview per FLOW listing and choose per row whether to create the
 *  listing or skip it, with an optional unit override. */
export function FlowImport() {
  const t = useTranslations("Broker");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<FlowImportRun | null>(null);
  const [decisions, setDecisions] = useState<Record<number, RowDecision>>({});
  const [properties, setProperties] = useState<Property[]>([]);
  const [unitsByProperty, setUnitsByProperty] = useState<Record<string, Unit[]>>({});
  const [result, setResult] = useState<FlowImportRun | null>(null);

  async function loadProperties() {
    if (properties.length > 0) return properties;
    const res = await bff<Property[]>("/api/bff/properties");
    const list = res.ok ? res.data : [];
    setProperties(list);
    return list;
  }

  async function loadUnits(propertyId: string) {
    if (unitsByProperty[propertyId]) return unitsByProperty[propertyId];
    const res = await bff<Unit[]>(`/api/bff/properties/${propertyId}/units`);
    const list = res.ok ? res.data : [];
    setUnitsByProperty((m) => ({ ...m, [propertyId]: list }));
    return list;
  }

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const body = new FormData();
    body.append("file", file);
    const res = await bff<FlowImportRun>("/api/bff/letting/flow-import/preview", { method: "POST", body });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRun(res.data);
    const initial: Record<number, RowDecision> = {};
    for (const row of res.data.rows) {
      initial[row.index] = {
        action: row.match.unit_id ? "create" : "skip",
        unitId: row.match.unit_id,
        propertyId: row.match.property_id,
      };
    }
    setDecisions(initial);
    await loadProperties();
  }

  function setDecision(index: number, patch: Partial<RowDecision>) {
    setDecisions((d) => ({
      ...d,
      [index]: { action: "skip", unitId: null, propertyId: null, ...d[index], ...patch },
    }));
  }

  async function onPropertyChange(index: number, propertyId: string) {
    setDecision(index, { propertyId: propertyId || null, unitId: null });
    if (propertyId) await loadUnits(propertyId);
  }

  async function apply() {
    if (!run) return;
    const toCreate = Object.entries(decisions).filter(([, d]) => d.action === "create");
    if (!window.confirm(t("import.confirmApply", { count: toCreate.length }))) return;
    setBusy(true);
    setError(null);
    const items = Object.entries(decisions).map(([index, d]) => ({
      index: Number(index),
      action: d.action,
      ...(d.action === "create" && d.unitId ? { unit_id: d.unitId } : {}),
    }));
    const res = await bff<FlowImportRun>(`/api/bff/letting/flow-import/${run.id}/apply`, {
      method: "POST",
      body: JSON.stringify({ items }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    setRun(res.data);
  }

  return (
    <div className="flex flex-col gap-5">
      <form onSubmit={upload} className="flex flex-wrap items-end gap-3" data-testid="flow-import-upload">
        <div>
          <label htmlFor="flow-dump" className={ui.label}>
            {t("import.file")}
          </label>
          <input
            id="flow-dump"
            type="file"
            accept=".sql,.txt"
            className={ui.input}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <button type="submit" className={ui.primary} disabled={!file || busy}>
          {t("import.upload")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p role="status" className={ui.notice} data-testid="flow-import-result">
          {t("import.resultSummary", { created: result.created_count, skipped: result.skipped_count })}
        </p>
      ) : null}
      {run ? (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="flow-import-preview">
            <thead>
              <tr>
                <th>{t("import.flowNumber")}</th>
                <th>{t("listingTitle")}</th>
                <th>{t("import.kind")}</th>
                <th>Status</th>
                <th className="text-right">{t("price")}</th>
                <th>{t("import.match")}</th>
                <th>{t("import.problems")}</th>
                <th>{t("import.action")}</th>
              </tr>
            </thead>
            <tbody>
              {run.rows.map((row) => {
                const decision = decisions[row.index] ?? { action: "skip", unitId: null, propertyId: null };
                const applied = Boolean(row.applied);
                return (
                  <tr key={row.index} data-testid={`flow-import-row-${row.index}`}>
                    <td>{row.external_ref}</td>
                    <td>{row.title ?? "—"}</td>
                    <td>{t(`create.kind${row.kind === "rental" ? "Rental" : "Sale"}`)}</td>
                    <td>{t(`status.${row.status}`)}</td>
                    <td className="text-right tabular-nums">{row.listing_fields.price ?? "—"}</td>
                    <td>
                      <select
                        aria-label={t("import.property")}
                        className={ui.input}
                        value={decision.propertyId ?? ""}
                        disabled={applied}
                        onChange={(e) => onPropertyChange(row.index, e.target.value)}
                      >
                        <option value="">{t("import.selectProperty")}</option>
                        {properties.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.number} {p.name}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label={t("import.unit")}
                        className={ui.input}
                        value={decision.unitId ?? ""}
                        disabled={applied || !decision.propertyId}
                        onChange={(e) => setDecision(row.index, { unitId: e.target.value || null })}
                      >
                        <option value="">{t("import.selectUnit")}</option>
                        {(unitsByProperty[decision.propertyId ?? ""] ?? []).map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.label ?? u.number}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="text-sm text-muted">
                      {row.problems.length > 0 ? (
                        <ul>
                          {row.problems.map((p) => (
                            <li key={p}>{p}</li>
                          ))}
                        </ul>
                      ) : null}
                    </td>
                    <td>
                      {applied ? (
                        <span className={ui.badge}>{t(`import.outcome.${row.outcome ?? "skipped"}`)}</span>
                      ) : (
                        <select
                          aria-label={t("import.action")}
                          className={ui.input}
                          value={decision.action}
                          onChange={(e) => setDecision(row.index, { action: e.target.value as "create" | "skip" })}
                        >
                          <option value="create">{t("import.actionCreate")}</option>
                          <option value="skip">{t("import.actionSkip")}</option>
                        </select>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="p-3">
            <button type="button" className={ui.primary} disabled={busy} onClick={apply}>
              {t("import.apply")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
