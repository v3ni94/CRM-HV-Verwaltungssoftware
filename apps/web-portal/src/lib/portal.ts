/**
 * Payload types of the portal endpoints (/api/v1/portal/*). The API answers with untyped
 * JSON objects (dict[str, Any] in apps/api/src/mhvp/portal/routers.py); the shapes here
 * mirror that contract field by field.
 */

export type PortalContract = {
  id: string;
  kind: string;
  number: string;
  unit_id: string | null;
  start_date: string | null;
  end_date: string | null;
};

export type PortalMe = {
  contact_id: string;
  roles: string[];
  contracts: PortalContract[];
};

export type PortalDocument = {
  id: string;
  title: string;
  filename: string;
  created_at: string;
};

export type PortalTicket = {
  id: string;
  number: string;
  title: string;
  status: string;
  comments: string[];
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

export type PortalWorkOrder = {
  id: string;
  description: string;
  status: string;
  quote_amount: string | null;
  scheduled_at: string | null;
};

/** Mieter oder Eigentümer mit mindestens einem Vertrag. */
export function hasContracts(me: PortalMe): boolean {
  return me.contracts.length > 0;
}

export function isProvider(me: PortalMe): boolean {
  return me.roles.includes("provider");
}

/** Beteiligter eines Übergabeprotokolls (access_grant scope_type handover, role participant). */
export function isHandoverParticipant(me: PortalMe): boolean {
  return me.roles.includes("participant");
}

/** German labels for the TicketStatus values of the API. */
export const TICKET_STATUS_LABELS: Record<string, string> = {
  new: "Neu",
  in_progress: "In Bearbeitung",
  waiting: "Wartet",
  done: "Erledigt",
  closed: "Geschlossen",
  rejected: "Abgelehnt",
};

/** German labels for the OrderStatus values of the API. */
export const ORDER_STATUS_LABELS: Record<string, string> = {
  draft: "Entwurf",
  requested: "Angefragt",
  quoted: "Angebot abgegeben",
  approved: "Freigegeben",
  scheduled: "Termin geplant",
  in_progress: "In Ausführung",
  done: "Ausgeführt",
  invoiced: "Rechnung eingereicht",
  accepted: "Abgenommen",
  rejected: "Abgelehnt",
  cancelled: "Storniert",
};

export function ticketStatusLabel(status: string): string {
  return TICKET_STATUS_LABELS[status] ?? status;
}

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status] ?? status;
}
