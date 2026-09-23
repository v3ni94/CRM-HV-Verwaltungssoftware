/** Types and helpers of the Immoware24 import assistant (M8, section 13.1). */
import type { components } from "@mhvp/api-client";

type S = components["schemas"];

export type ReportType = S["ReportType"];
export type ImportField = S["FieldOut"];
export type ImportMapping = S["MappingOut"];
export type ImportSource = S["SourceOut"];
export type StagingRow = S["RowOut"];
export type RowStatus = S["RowStatus"];

/** Wizard order: recommended import order first, then the staged only reports. */
export const REPORT_TYPES: ReportType[] = [
  "properties",
  "units",
  "contacts",
  "ownerships",
  "tenancies",
  "payments",
  "journal",
  "bank_transactions",
];

/** Reports without target fields: rows are only staged until the ledger exists (18, M8). */
export const STAGED_ONLY: ReportType[] = ["journal", "bank_transactions"];

export const ROW_STATUSES: RowStatus[] = ["pending", "valid", "invalid", "unchanged", "conflict", "created", "staged_only"];

export const API = "/api/bff/imports/immoware24";

export type RunProblem = { row: number; status: string; messages: string[] };
/** Result of test run and apply as built by mhvp.imports.services.run. */
export type RunReport = {
  test_run?: boolean;
  counts: Record<string, number>;
  problems: RunProblem[];
  sums?: { source_gross: string; created_gross: string };
};
export type UnitsPerProperty = Record<string, { file: number; platform: number; difference: number }>;
/** Reconciliation as built by mhvp.imports.services.reconcile. */
export type Reconciliation = {
  rows: number;
  status: Record<string, number>;
  units_per_property?: UnitsPerProperty;
  open_differences: number;
};

/** Distinct non empty values of one source column, in order of appearance. */
export function distinctValues(rows: Pick<StagingRow, "raw">[], header: string, max = 50): string[] {
  const seen = new Set<string>();
  for (const row of rows) {
    const value = row.raw[header];
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) seen.add(text);
    if (seen.size >= max) break;
  }
  return [...seen];
}

/** Required target fields without an assigned source column. */
export function missingRequired(fields: ImportField[], columns: Record<string, string>): ImportField[] {
  return fields.filter((f) => f.required && !columns[f.name]);
}

/** Drops empty assignments so that only chosen columns and value mappings are saved. */
export function cleanMapping(
  columns: Record<string, string>,
  valueMaps: Record<string, Record<string, string>>,
): { columns: Record<string, string>; value_maps: Record<string, Record<string, string>> } {
  const cols = Object.fromEntries(Object.entries(columns).filter(([, v]) => v));
  const maps: Record<string, Record<string, string>> = {};
  for (const [field, map] of Object.entries(valueMaps)) {
    if (!cols[field]) continue;
    const entries = Object.entries(map).filter(([, v]) => v);
    if (entries.length) maps[field] = Object.fromEntries(entries);
  }
  return { columns: cols, value_maps: maps };
}
