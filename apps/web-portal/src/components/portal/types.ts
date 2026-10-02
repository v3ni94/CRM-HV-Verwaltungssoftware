/** Shapes of /api/v1/portal/* (M21 Mieter und Eigentümer, M22 Dienstleister). Internal CRM
 *  fields are never part of these responses. */

export type Me = {
  contact_id: string;
  roles: string[];
  /** S16-10 (3.4): named portal roles derived from the relations (role switch). */
  portal_roles?: string[];
  contracts: {
    id: string;
    kind: string;
    number: string;
    unit_id: string | null;
    start_date: string | null;
    end_date: string | null;
  }[];
  /** Portal permissions of a staff account (M2-08); absent or empty for external users. */
  permissions?: string[];
  /** M21-08: Funktionsschalter des Mandanten (Chat, KI-Vorqualifizierung, Support-Sicht). */
  features?: { chat_enabled: boolean; chat_ai_prequalification_enabled: boolean; support_login_enabled: boolean; owner_rental_income_enabled?: boolean; owner_ticket_scope?: string; chat_bot_enabled?: boolean; privacy_feature_enabled?: boolean };
  /** M21-05: Vollmachten dieses Zugangs (Vertreterrolle). */
  representations?: { id: string; principal_contact_id: string; valid_from: string; valid_to: string | null }[];
};

/** M21-05: eigene Vertretung mit Zustand und Restlaufzeit (GET /api/v1/portal/representations). */
export type PortalRepresentation = {
  id: string;
  principal_contact_id: string;
  principal_name: string | null;
  valid_from: string;
  valid_to: string | null;
  state: "active" | "pending" | "expired" | "revoked";
  expires_in_days: number | null;
};

/** M21-01: Nachricht im Chat zur Meldung. */
export type ChatMessage = {
  id: string;
  direction: "own" | "management";
  body: string;
  created_at: string;
};

/** M21-06, SA-05: beschlossene Zahlung der Gemeinschaft (Information, keine Zahlung). */
export type PaymentResolution = {
  resolution_id: string;
  number: number;
  decided_on: string;
  subject: string;
  kind: "economic_plan" | "special_levy";
  legal_entity_name: string | null;
  valid_from: string | null;
  valid_to: string | null;
  rhythm: string | null;
  due_day: number | null;
  instalments: number | null;
  total: string | null;
  purpose: string | null;
  sepa: { holder: string; iban: string; bic: string | null; bank_name: string | null } | null;
  /** Own amounts from the calculated snapshot (M21-06, SA-05); null while not calculated. */
  own_share?:
    | { unit_number: string; annual?: Record<string, string>; monthly?: Record<string, string>; amount?: string; instalments?: number | null }[]
    | null;
};

export type OwnerAllocationUnit = {
  unit_id: string;
  unit_number: string;
  property_name: string;
  keys: { code: string; name: string; unit_of_measure: string; kind: string; value: string | null }[];
};

export type OwnerRentalIncome = {
  property_id: string;
  property_name: string;
  total_gross: string;
  units: { unit_number: string; gross: string; components: { payment_type_code: string; gross: string }[] }[];
};

export type OwnerTakeoverProperty = {
  property_id: string;
  property_name: string;
  open_count: number;
  complete: boolean;
  points: { category: string; label: string; status: string; status_label: string; due_date: string | null }[];
};

export type OwnerTicket = { id: string; number: number; title: string; status: string; created_at: string };

export function isProvider(me: Me): boolean {
  return me.roles.includes("provider");
}

/** Roles whose portal account can carry a handover grant (M30 Stufe 3): participants and
 *  helpers invited from the protocol, tenants and owners with a protocol of their own. Staff
 *  with the portal permission handover:read see the tenant wide list. The navigation entry
 *  and the start tile use this one rule (M31 WP5), so both stay in sync. */
const HANDOVER_ROLES = ["helper", "participant", "tenant", "owner", "tenant_or_owner"];

export function showsHandover(me: Me): boolean {
  if (isProvider(me)) return false;
  if (me.permissions?.includes("handover:read")) return true;
  return me.roles.some((role) => HANDOVER_ROLES.includes(role));
}

export type PortalDocument = {
  id: string;
  title: string;
  filename: string;
  created_at: string;
  /** M21-02, SA-06: neu, solange der Nutzer das Dokument nicht geöffnet hat (Indiz, keine Zustellung). */
  is_new?: boolean;
  last_opened_at?: string | null;
  context?: string | null;
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
  completed_work_order_ids?: string[];
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

/** Regel H03: monatliche Verbrauchsinformation der eigenen Einheit (nur Werte, keine
 *  Betreibervermerke). */
export type ConsumptionComponent = {
  value: string;
  unit_of_measure: string | null;
  kind?: string;
  source?: string;
  units?: number;
};

export type ConsumptionInfoRow = {
  id: string;
  unit_id: string;
  month: string;
  values: {
    month: string;
    period_from: string;
    period_to: string;
    heating: ConsumptionComponent | null;
    hot_water: ConsumptionComponent | null;
    previous_month: { heating?: ConsumptionComponent | null; hot_water?: ConsumptionComponent | null } | null;
    previous_year_month: { heating?: ConsumptionComponent | null; hot_water?: ConsumptionComponent | null } | null;
    property_average: { heating?: ConsumptionComponent | null; hot_water?: ConsumptionComponent | null } | null;
  };
  estimated: string[];
  created_at: string;
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
  /** A77: accounts of the booked entry and the vendor behind the invoice (filter values). */
  accounts?: { id: string; number: string; name: string }[];
  vendor_contact_id?: string | null;
  vendor_name?: string | null;
};

/** A77: server side filter of the audit room positions (query parameters of the detail). */
export type BoardFilter = {
  account_id: string | null;
  vendor_contact_id: string | null;
  date_from: string | null;
  date_to: string | null;
  q: string | null;
};

export type BoardFilterOptions = {
  accounts: { id: string; number: string; name: string }[];
  vendors: { id: string; name: string }[];
};

/** A76: statement of the board on one report version (text only, no release effect). */
export type BoardStatement = {
  text: string | null;
  recorded_at: string | null;
  recorded_by_account: string | null;
  source: string;
};

export type BoardReport = {
  id: string;
  engagement_id: string;
  version: number;
  created_at: string;
  content: {
    date?: string | null;
    sampling?: string | null;
    scope_note?: string | null;
    overall_status?: string | null;
    selected?: number | null;
    checked_count?: number | null;
    checked_value?: string | null;
    unchecked_count?: number | null;
    unchecked_value?: string | null;
    findings?: string | null;
    recommendation?: string | null;
  };
  board_statement: BoardStatement | null;
  board_statement_history: BoardStatement[];
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
  positions_total?: number;
  filter?: BoardFilter;
  filter_options?: BoardFilterOptions;
  cost_items: { id: string; label: string; amount: string; basis: string }[];
  documents: { id: string; title: string; filename: string; mime_type: string; created_at: string; audit_item_id: string | null }[];
  notes: BoardNote[];
  read_receipt_note: string;
};

/** Formularvorlage der Verwaltung (A56), ohne CRM Felder (Kategorie, Aktivstatus). */
export type PortalFormField = {
  key: string;
  label: string;
  type:
    | "text"
    | "textarea"
    | "number"
    | "date"
    | "time"
    | "select"
    | "radio"
    | "multiselect"
    | "checkbox"
    | "email"
    | "phone"
    | "file"
    | "address"
    | "location"
    | "signature"
    | "consent"
    | "amount"
    | "heading"
    | "info"
    | "divider";
  required: boolean;
  options?: string[] | null;
  help?: string | null;
};

export type PortalForm = {
  id: string;
  name: string;
  description: string | null;
  audience: "tenant" | "owner" | "all";
  fields: PortalFormField[];
};

/** M25-03 / V13: Versammlung der eigenen Gemeinschaft; Einwahldaten nur bei hybrider oder
 *  virtueller Form nach Einladung und nur für Eigentümer. */
export type PortalMeeting = {
  id: string;
  legal_entity_name: string | null;
  kind: string;
  mode: string;
  mode_label: string;
  scheduled_at: string;
  location: string | null;
  public_description?: string | null;
  ends_at?: string | null;
  status: string;
  invited_at: string | null;
  notice: string | null;
  dial_in_url: string | null;
  dial_in_access: string | null;
  dial_in_note: string | null;
};

/** AD06 / GA11-03: meeting detail with online participation (switch off by default). Results
 *  only after the announcement; while voting, only the markers of the own units. */
export type PortalMeetingItem = {
  id: string;
  position: number;
  title: string;
  proposal: string | null;
  voting_state: "not_opened" | "open" | "closed" | "announced";
  voted_contract_ids: string[];
  result: { status: string; votes: { yes?: string; no?: string; abstain?: string } | null } | null;
};

export type PortalMeetingDetail = {
  id: string;
  mode: string;
  status: string;
  online_enabled: boolean;
  online_note: string;
  conference_url: string | null;
  conference_access: string | null;
  own_contract_ids: string[];
  confirmed_contract_ids: string[];
  represented_contract_ids: string[];
  units: { contract_id: string; unit_number: string; own: boolean }[];
  items: PortalMeetingItem[];
  speaker_requests: { id: string; requested_at: string; status: string; agenda_item_id: string | null }[];
};

/** M19-02: submission to the board as the portal shows it (no CRM user ids, no other member's
 *  comments beyond the tally). */
export type PortalBoardSubmission = {
  id: string;
  kind: "info" | "consent";
  title: string;
  note: string | null;
  amount: string | null;
  due_on: string;
  status: "open" | "closed";
  overdue: boolean;
  can_vote: boolean;
  tally: { approve: number; reject: number; comment: number };
  member_count: number;
  my_votes: { id: string; vote: "approve" | "reject" | "comment"; comment: string | null; created_at: string }[];
  created_at: string;
};

/** AE28 (M7-06): Portal-Assistent, Antworten nur aus den für den Zugang freigegebenen Unterlagen. */
export type AssistantStatus = {
  enabled: boolean;
  privacy: {
    feature_enabled: boolean;
    notice_status: "not_required" | "released" | "not_released";
    title: string | null;
    body: string | null;
    version: number | null;
    acknowledged: boolean;
  };
  ai: { available: boolean; blocked_code: string | null; blocked_message: string | null };
  scope: { units: number; documents: number };
  hourly_limit: number;
  notice: string;
  emergency_note: string;
};

export type AssistantScopeView = {
  focus_unit_id: string | null;
  units: { id: string; number: string; label: string | null }[];
  documents: { document_id: string; title: string }[];
  total_documents: number;
};

export type AssistantAnswer = {
  id: string;
  mode: "ai" | "search";
  status: "answered" | "not_answerable" | "failed" | "search_hits" | "no_sources" | "pending" | "timeout";
  answer: string | null;
  sources: { document_id: string; title: string; excerpt?: string | null }[];
  hits: { document_id: string; title: string }[];
  ai_available: boolean;
  ai_blocked_code: string | null;
  ai_blocked_reason: string | null;
  notice: string;
  emergency_note: string;
  created_at: string;
};

export type AssistantHistoryRow = {
  id: string;
  question: string;
  answer: string | null;
  mode: "ai" | "search";
  status: AssistantAnswer["status"];
  sources: { document_id: string; title: string }[];
  created_at: string;
};
