/** Types and helpers of the AI assistant screens (M7, sections 9 and 10). */
import type { components } from "@mhvp/api-client";

type S = components["schemas"];

export type Conversation = S["ConversationOut"];
export type Message = S["MessageOut"];
export type Run = S["RunOut"];
export type Proposal = S["ProposalOut"];
export type ImportRun = S["ImportOut"];
export type ImportItem = S["ImportItemOut"];
export type Usage = S["UsageOut"];
export type Provider = S["mhvp__ai__schemas__ProviderOut"];
export type ProviderIn = S["mhvp__ai__schemas__ProviderIn"];
export type ContactChoice = S["ContactChoice"];
export type PropertyChoice = S["PropertyChoice"];
export type DocumentOut = S["DocumentOut"];

export const CHAT_TASKS = ["extract_contacts", "extract_property", "answer_question", "summarize"] as const;
export type ChatTask = (typeof CHAT_TASKS)[number];

export const POLL_INTERVAL_MS = 2000;

export function isRunPending(run: Pick<Run, "status">): boolean {
  return run.status === "queued" || run.status === "running";
}

/** Contact preview row as built by the API (mhvp.ai.imports.contacts_preview). */
export type ContactRowStatus = "new" | "existing" | "incomplete" | "invalid";
export type DuplicateHit = { contact_id: string; name: string; score: number; reasons: string[] };
export type ContactRow = {
  index: number;
  status: ContactRowStatus;
  contact: Record<string, unknown> | null;
  role: string | null;
  unit_number: string | null;
  co_members: string[];
  confidence: number | null;
  source_row: number | null;
  duplicates: DuplicateHit[];
  notes: string[];
};
export type ContactsPreview = { rows: ContactRow[]; questions: string[] };

/** Property preview as built by the API (mhvp.ai.imports.property_preview). */
export type PropertyPayment = { payment_type_code: string; gross: string; valid_from: string | null };
export type PropertyParty = {
  role: "owner" | "tenant";
  unit_number: string;
  kind: "person" | "company";
  salutation: string | null;
  first_name: string | null;
  last_name: string | null;
  company_name: string | null;
  start_date: string | null;
  payments: PropertyPayment[];
  source: string | null;
  confidence: number | null;
};
export type PropertyUnit = {
  number: string;
  label: string | null;
  building: string | null;
  location: string | null;
  unit_type: string;
  living_area_sqm: string | null;
  mea: string | null;
  source: string | null;
  confidence: number | null;
};
export type PropertyPreview = {
  property: {
    number?: string | null;
    name?: string | null;
    management_type?: "rental" | "hoa" | "hoa_with_sev" | null;
    street?: string | null;
    house_number?: string | null;
    postal_code?: string | null;
    city?: string | null;
  };
  buildings: string[];
  units: PropertyUnit[];
  parties: PropertyParty[];
  questions: string[];
  notes: string[];
};

export function contactsPreview(proposed: Record<string, unknown>): ContactsPreview {
  const p = proposed as Partial<ContactsPreview>;
  return { rows: Array.isArray(p.rows) ? p.rows : [], questions: Array.isArray(p.questions) ? p.questions : [] };
}

export function propertyPreview(proposed: Record<string, unknown>): PropertyPreview {
  const p = proposed as Partial<PropertyPreview>;
  return {
    property: p.property ?? {},
    buildings: p.buildings ?? [],
    units: p.units ?? [],
    parties: p.parties ?? [],
    questions: p.questions ?? [],
    notes: p.notes ?? [],
  };
}

export function contactName(contact: Record<string, unknown> | null): string {
  if (!contact) return "";
  const parts = [contact.first_name, contact.last_name].filter((x) => typeof x === "string" && x);
  return (typeof contact.company_name === "string" && contact.company_name) || parts.join(" ");
}

export function partyName(party: PropertyParty): string {
  return party.company_name || [party.first_name, party.last_name].filter(Boolean).join(" ");
}

/** Distinct payment type codes of all parties, in first-seen order. */
export function paymentTypes(preview: PropertyPreview): string[] {
  const seen: string[] = [];
  for (const party of preview.parties) {
    for (const payment of party.payments) {
      if (!seen.includes(payment.payment_type_code)) seen.push(payment.payment_type_code);
    }
  }
  return seen;
}

/**
 * VAT inputs -> apply map. An empty input is left out on purpose: the API then does not create
 * the payment (no rate is ever derived by the platform, S01). Returns the codes with an
 * invalid entry separately so the UI can block the confirmation.
 */
export function vatMap(inputs: Record<string, string>): { map: Record<string, string>; invalid: string[] } {
  const map: Record<string, string> = {};
  const invalid: string[] = [];
  for (const [code, raw] of Object.entries(inputs)) {
    const value = raw.trim().replace(",", ".");
    if (value === "") continue;
    if (!/^\d{1,2}(\.\d{1,2})?$/.test(value)) {
      invalid.push(code);
      continue;
    }
    map[code] = value;
  }
  return { map, invalid };
}

/** Pulls sources, notes and open questions out of a run output for the "Warum?" disclosure. */
export type Reasoning = { sources: { document_id: string; excerpt: string }[]; notes: string[]; questions: string[] };

export function reasoningOf(output: Record<string, unknown> | null | undefined): Reasoning {
  const o = (output ?? {}) as Record<string, unknown>;
  const list = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
  const sources = Array.isArray(o.sources)
    ? (o.sources as { document_id?: unknown; excerpt?: unknown }[])
        .filter((x) => typeof x?.document_id === "string")
        .map((x) => ({ document_id: String(x.document_id), excerpt: String(x.excerpt ?? "") }))
    : [];
  return { sources, notes: list(o.notes), questions: [...list(o.questions), ...list(o.open_points)] };
}
