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
/** Report types added in Welle 3 (M8-02 to M8-07); typed separately until the API client is regenerated. */
const WAVE3_REPORT_TYPES = [
  "chart_of_accounts",
  "sepa_overview",
  "bank_history",
  "open_items",
  "document_index",
  "ticket_history",
] as unknown as ReportType[];

/** Report types added in Welle 5 (M8-01); typed separately until the API client is regenerated. */
const WAVE5_REPORT_TYPES = [
  "deposit",
  "allocation_key",
  "meter",
  "energy_certificate",
  "service_provider",
  "portal_user",
] as unknown as ReportType[];

/** Report types added in Welle 23 (GAJ-501): filed and checked only, nothing posts. */
const WAVE23_REPORT_TYPES = ["historical_statement", "resolution"] as unknown as ReportType[];

export const REPORT_TYPES: ReportType[] = [
  "properties",
  "units",
  "contacts",
  "ownerships",
  "tenancies",
  "payments",
  "journal",
  "bank_transactions",
  ...WAVE3_REPORT_TYPES,
  ...WAVE5_REPORT_TYPES,
  ...WAVE23_REPORT_TYPES,
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
  sums?: { source_gross?: string; created_gross?: string; source_amount?: string; created_amount?: string; field?: string };
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

/* AE37 (Q08-01): header heuristic, stored assignments, validation report, export status.
   Typed by hand until the API client is regenerated (make openapi). */

export type HeaderCandidate = {
  row: number;
  score: number;
  filled: number;
  text_cells: number;
  matched_terms: string[];
  duplicates: string[];
  reason: string;
};
/** POST /imports/immoware24/header-detection */
export type HeaderDetection = {
  header_row: number | null;
  headers: string[];
  sheet: string | null;
  sheets: string[];
  rows_scanned: number;
  candidates: HeaderCandidate[];
};

export type ProposalStatus = "stored" | "sure" | "check" | "none";
export type FieldProposal = {
  name: string;
  label: string;
  required: boolean;
  header: string | null;
  score: number;
  basis: string | null;
  basis_label: string | null;
  status: ProposalStatus;
  note: string | null;
  alternatives: { header: string; score: number; basis: string }[];
};
/** GET /imports/immoware24/files/{id}/column-proposal */
export type ColumnProposal = {
  report_type: ReportType;
  headers: string[];
  columns: Record<string, string>;
  fields: FieldProposal[];
  unassigned_headers: string[];
  ignored_headers: string[];
  missing_required: string[];
  stored_used: number;
};

export type RequiredStatus = "ok" | "partly_empty" | "empty" | "missing" | "not_in_file";
export type CheckSampleRow = {
  row_number: number;
  raw: Record<string, unknown>;
  values: Record<string, unknown>;
  errors: string[];
};
/** POST /imports/immoware24/files/{id}/check (read only validation report). */
export type ColumnCheck = {
  report_type: ReportType;
  rows: number;
  valid: number;
  invalid: number;
  staged_only: boolean;
  required: { name: string; label: string; header: string | null; status: RequiredStatus; empty: number }[];
  fields: { name: string; label: string; header: string | null; filled: number; empty: number; errors: number; examples: string[] }[];
  not_in_file: string[];
  assigned_twice: string[];
  unassigned_headers: string[];
  sample_rows: CheckSampleRow[];
  error_rows: CheckSampleRow[];
  ready: boolean;
};

/** GET/PUT /imports/immoware24/column-assignments */
export type ColumnAssignment = {
  id: string;
  report_type: ReportType;
  header: string;
  header_key: string;
  target_field: string | null;
  use_count: number;
  last_used_at: string | null;
  updated_at: string;
};

export type RequirementStatus = "file_missing" | "mapping_open" | "mapping_stored" | "applied";
/** GET /imports/immoware24/export-requirements */
export type ExportRequirement = {
  report_type: ReportType;
  source: string;
  required_fields: string[];
  optional_fields: string[];
  stored_assignments: number;
  required_covered: string[];
  files: number;
  last_file_at: string | null;
  last_headers: number | null;
  applied: boolean;
  status: RequirementStatus;
};

/** Proposed columns limited to headers of the file (a stale proposal never adds others). */
export function proposedColumns(proposal: ColumnProposal, headers: string[]): Record<string, string> {
  return Object.fromEntries(Object.entries(proposal.columns).filter(([, h]) => headers.includes(h)));
}

/** Assignments to remember: every chosen column of the mapping (header -> target field);
 *  a header chosen for two fields is remembered for the first one only. */
export function assignmentsFrom(columns: Record<string, string>): { header: string; target_field: string }[] {
  const byHeader = new Map<string, string>();
  for (const [field, header] of Object.entries(columns)) {
    if (header && !byHeader.has(header)) byHeader.set(header, field);
  }
  return [...byHeader].map(([header, field]) => ({ header, target_field: field }));
}
