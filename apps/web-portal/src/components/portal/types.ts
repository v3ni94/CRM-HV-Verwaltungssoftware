/** Shapes of /api/v1/portal/* (M21 Mieter und Eigentümer, M22 Dienstleister). Internal CRM
 *  fields are never part of these responses. */

export type Me = {
  contact_id: string;
  roles: string[];
  contracts: {
    id: string;
    kind: string;
    number: string;
    unit_id: string | null;
    start_date: string | null;
    end_date: string | null;
  }[];
};

export function isProvider(me: Me): boolean {
  return me.roles.includes("provider");
}

export type PortalDocument = {
  id: string;
  title: string;
  filename: string;
  created_at: string;
};

export type Attachment = {
  id: string;
  title: string;
  filename: string;
  mime_type: string;
};

/** A58: Terminvorschlag eines Dienstleisters zum Auftrag. */
export type AppointmentProposal = {
  id: string;
  work_order_id: string;
  starts_at: string;
  note: string | null;
  status: "proposed" | "accepted" | "declined" | "superseded";
  decided_at: string | null;
};

export type Ticket = {
  id: string;
  number: string;
  title: string;
  status: string;
  comments: string[];
  attachments: Attachment[];
  appointment_proposals: AppointmentProposal[];
};

export type AccountItem = {
  contract_number: string;
  due_date: string;
  amount: string;
  remaining: string;
};

export type AccountStatement = {
  items: AccountItem[];
  note: string | null;
};

export type WorkOrder = {
  id: string;
  description: string;
  status: string;
  quote_amount: string | null;
  scheduled_at: string | null;
  appointment_proposals: AppointmentProposal[];
  photos: Attachment[];
};

/** TT.MM.JJJJ HH:MM in Europe/Berlin (UI format, internally ISO 8601). */
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("de-DE", {
    timeZone: "Europe/Berlin",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export const TICKET_STATUS = ["new", "in_progress", "waiting", "done", "closed", "rejected"] as const;

export const ORDER_STATUS = [
  "draft",
  "requested",
  "quoted",
  "approved",
  "scheduled",
  "in_progress",
  "done",
  "invoiced",
  "accepted",
  "rejected",
  "cancelled",
] as const;

/** Eigentümerportal (A51, section 14 role owner), read only. */
export type PortalResolution = {
  id: string;
  number: number;
  decided_on: string;
  subject: string;
  wording: string;
  status: string;
  kind: string;
  majority_basis: string | null;
  votes: { principle: string | null; yes: string; no: string; abstain: string } | null;
  legal_entity_name: string | null;
};

export type PropertyContacts = {
  property_id: string;
  property_number: string;
  property_name: string;
  address: string | null;
  manager_name: string | null;
  contacts: { category: string; name: string; phones: string[] }[];
};

export type HoaAccountEntry = {
  booking_date: string;
  due_date: string | null;
  text: string;
  kind: string;
  direction: "charge" | "credit";
  amount: string;
  reversed: boolean;
};

export type HoaAccountContract = {
  contract_number: string;
  entries: HoaAccountEntry[];
  charges: string | null;
  credits: string | null;
  balance: string | null;
  note: string | null;
};

export type HoaAccount = {
  contracts: HoaAccountContract[];
  note: string;
  legacy_note: string | null;
};

export const RESOLUTION_STATUS = [
  "positive",
  "negative",
  "final",
  "contested",
  "annulled",
  "legally_binding",
  "void",
] as const;

/** Prüfungsraum des Beirats (7.9.2, A52): /api/v1/portal/board/*. */
export type BoardEngagement = {
  id: string;
  legal_entity_id: string;
  legal_entity_name: string | null;
  statement_id: string | null;
  period_from: string;
  period_to: string;
  purpose: string;
  sampling: string;
  status: string;
  snapshot_hash: string | null;
  granted_at?: string;
  open_questions?: number;
};

export type BoardPosition = {
  id: string;
  journal_entry_id: string | null;
  document_id: string | null;
  amount: string | null;
  status: string;
  note: string | null;
  question: string | null;
  answer: string | null;
  outdated_reason: string | null;
  booking_date: string | null;
  booking_text: string | null;
  booking_reference: string | null;
};

export type BoardNote = {
  id: string;
  engagement_id: string;
  audit_item_id: string | null;
  cost_item_id: string | null;
  kind: string;
  text: string;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
};

export type BoardEngagementDetail = BoardEngagement & {
  overall_status: string;
  population: Record<string, unknown>;
  positions: BoardPosition[];
  cost_items: { id: string; label: string; amount: string; basis: string }[];
  documents: { id: string; title: string; filename: string; mime_type: string; created_at: string; audit_item_id: string | null }[];
  notes: BoardNote[];
  read_receipt_note: string;
};

/** Formularvorlage der Verwaltung (A56), ohne CRM Felder (Kategorie, Aktivstatus). */
export type PortalFormField = {
  key: string;
  label: string;
  type: "text" | "number" | "date" | "select" | "file";
  required: boolean;
  options?: string[] | null;
};

export type PortalForm = {
  id: string;
  name: string;
  description: string | null;
  audience: "tenant" | "owner" | "all";
  fields: PortalFormField[];
};
