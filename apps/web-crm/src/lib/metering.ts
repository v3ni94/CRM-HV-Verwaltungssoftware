/** Types and small helpers of the Messdienstleister UI (module mhvp.metering, stage 1).
 *  All business identifiers (customer, billing unit, Nutzeinheit numbers) are strings so that
 *  leading zeros survive; nothing here parses them as numbers. */
import { problemMessage, readProblem } from "./problem";

export type ProviderFunction = {
  function: string;
  documented_support: "yes" | "documentation_required" | "unclear" | "no" | string;
  label: string;
  source: string;
  note: string;
  adapter_implemented: boolean;
};

export type MeteringProvider = {
  code: string;
  name: string;
  manual_only: boolean;
  functions: ProviderFunction[];
  sources: Record<string, string>;
  research_note: string;
  auth_note: string;
};

export type Capability = {
  function: string;
  documented_support: string;
  documented_note: string;
  adapter_implemented: boolean;
  supported_version: string | null;
  account_release: boolean;
  last_test_result: unknown;
  last_test_at: string | null;
  test_stale: boolean;
  released_by_last_test: boolean;
  available: boolean;
  reason: string | null;
  label: string;
};

export type MeteringConnection = {
  id: string;
  display_name: string;
  provider_code: string;
  contracting_company: string | null;
  environment: string;
  status: string;
  customer_references: string[];
  config: Record<string, unknown>;
  secret_names: string[];
  capabilities: Capability[];
  last_test_status: string | null;
  last_test_at: string | null;
  last_test_detail: string | null;
  test_stale: boolean;
  scheduled_sync_enabled: boolean;
  write_sync_enabled: boolean;
  last_sync: Record<string, unknown>;
  version: number;
};

export type ConnectionTest = {
  outcome: string;
  detail: string;
  functions_released: string[];
  connection: MeteringConnection;
};

export type Assignment = {
  id: string;
  connection_id: string;
  connection_name: string;
  provider_code: string;
  environment: string;
  property_id: string;
  property_number: string;
  property_name: string;
  property_address: string | null;
  external_billing_unit_id: string;
  external_number: string;
  external_name: string | null;
  expected_unit_count: number | null;
  service_scope: string;
  valid_from: string;
  valid_to: string | null;
  status: string;
  origin: string;
  is_primary: boolean;
  confirmed_at: string | null;
  verification_basis: string | null;
  remote_confirmed: boolean;
  remote_confirmed_at: string | null;
  group_id: string | null;
  unit_scope: string[];
  assigned_unit_count: number;
  conflict_reason: string | null;
  error_hint: string | null;
  last_success_at: string | null;
  note: string | null;
  version: number;
};

export type UnitAssignment = {
  id: string;
  property_assignment_id: string;
  unit_id: string;
  unit_number: string;
  unit_location: string | null;
  unit_floor: string | null;
  external_unit_number: string;
  valid_from: string;
  valid_to: string | null;
  billing_recipient_contact_id: string | null;
  consumption_info_recipient_contact_id: string | null;
  occupancy_status: string;
  status: string;
  external_partner_ref: string | null;
  note: string | null;
  version: number;
};

export type SyncJob = {
  id: string;
  connection_id: string;
  data_kind: string;
  status: string;
  error_summary: string | null;
  finished_at: string | null;
  last_success_at: string | null;
  created_at: string;
};

export type ClearingItem = {
  id: string;
  connection_id: string;
  entity_type: string;
  external_identifier: string;
  reason: string;
  status: string;
  resolution_note: string | null;
  property_assignment_id: string | null;
  created_at: string;
};

export type ConsumptionValue = {
  id: string;
  unit_assignment_id: string | null;
  period_from: string;
  period_to: string;
  kind: string;
  unit_of_measure: string;
  reading_type: string;
  source: string;
  version: number;
  value: string | null;
  value_kind: string;
};

export type BillingResult = {
  id: string;
  unit_assignment_id: string | null;
  period_from: string;
  period_to: string;
  amount: string;
  currency: string;
  version: number;
  external_document_ref: string;
  review_status: string;
};

export type ImportRow = { line: number; status: string; messages: string[]; values: Record<string, string> };
export type ImportPreview = {
  ok_count: number;
  error_count: number;
  duplicate_count: number;
  rows: ImportRow[];
  created_ids: string[];
};

/** bved 3.10 Austauschdatei-Vorschau (POST /metering/connections/{id}/heiwako-import/preview). */
export type HeiwakoFile = {
  name: string;
  kind: string | null;
  record_counts: Record<string, number>;
  errors: string[];
  undocumented_record_types: string[];
};
export type HeiwakoBillingResult = {
  external_billing_unit: string;
  external_unit_number: string | null;
  period_from: string;
  period_to: string;
  amount: string;
  currency: string;
  external_document_ref: string;
  cost_type_key: string | null;
  balance_gross: string | null;
  prepayment_gross: string | null;
};
export type HeiwakoUser = {
  external_billing_unit: string | null;
  external_unit_number: string | null;
  client_ref: string | null;
  name: string | null;
  occupancy_from: string | null;
  occupancy_to: string | null;
  vacancy_flag: number | null;
};
export type HeiwakoPreview = {
  adapter: string;
  spec_version: string;
  files: HeiwakoFile[];
  billing_results: HeiwakoBillingResult[];
  users: HeiwakoUser[];
  property_count: number;
  reference_count: number;
  image_count: number;
  errors: string[];
  stored: boolean;
};

/** Unit of the property with current occupants (GET /properties/{id}/units?with_occupants=true). */
export type PropertyUnit = {
  id: string;
  number: string;
  label?: string | null;
  location?: string | null;
  floor?: string | null;
  living_area_sqm?: string | null;
  total_area_sqm?: string | null;
  owner?: { party_name: string; start_date: string; end_date: string | null } | null;
  tenant?: { party_name: string; start_date: string; end_date: string | null } | null;
};

export const SERVICE_SCOPES = ["heating", "hot_water", "cold_water", "smoke_detectors", "other"] as const;
export const ASSIGNMENT_STATUSES = ["open", "proposed", "confirmed", "conflict", "archived"] as const;
export const OCCUPANCY_STATUSES = ["occupied", "vacant", "owner_use", "unclear"] as const;
/** Data kinds that "Jetzt abrufen" offers; they map 1:1 to capability functions. */
export const DATA_KINDS = ["documents", "consumption", "billing_result", "billing_unit_data"] as const;

export function capabilityFor(connection: MeteringConnection | undefined, fn: string): Capability | undefined {
  return connection?.capabilities.find((c) => c.function === fn);
}

export type ListResult<T> = { ok: true; data: T[]; total: number } | { ok: false; message: string };

/** GET a list through the BFF and read X-Total-Count (server side pagination). */
export async function bffList<T>(path: string): Promise<ListResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", cache: "no-store" });
  } catch {
    return { ok: false, message: problemMessage(null, 0) };
  }
  if (!response.ok) {
    const problem = await readProblem(response);
    return { ok: false, message: problemMessage(problem, response.status) };
  }
  const data = (await response.json()) as T[];
  const total = Number(response.headers.get("x-total-count") ?? data.length);
  return { ok: true, data, total: Number.isFinite(total) ? total : data.length };
}

export function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Controlled write workflow record (section 12): GET/POST /metering/transmissions. */
export type Transmission = {
  id: string;
  connection_id: string;
  property_assignment_id: string;
  kind: "roles" | "billing_input" | "billing_unit_setup";
  period_from: string | null;
  period_to: string | null;
  status: string;
  fingerprint: string;
  assignment_version: number;
  validation: {
    errors?: string[];
    warnings?: string[];
    provider?: Record<string, unknown>;
    function_available?: boolean;
    function_reason?: string | null;
  };
  diff: { first_transmission?: boolean; added?: string[]; removed?: string[]; changed?: string[] };
  summary: Record<string, unknown>;
  payload: Record<string, unknown>;
  released_by: string | null;
  released_at: string | null;
  warnings_acknowledged: boolean;
  ordered_by: string | null;
  ordered_at: string | null;
  provider_transaction_id: string | null;
  provider_response: Record<string, unknown>;
  log: Record<string, unknown>[];
  version: number;
  created_at: string;
};

export const TRANSMISSION_KINDS = ["roles", "billing_input", "billing_unit_setup"] as const;

/** Preview row of the Ordnungsbegriffsabgleich (summary.units of kind billing_unit_setup). */
export type SetupUnitRow = {
  unit_number: string;
  unit_label: string | null;
  external_unit_number: string;
  occupancy_status: string;
  known_at_provider: boolean;
  matched: boolean | null;
};
