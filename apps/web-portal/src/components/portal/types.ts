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

export type Ticket = {
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

export type WorkOrder = {
  id: string;
  description: string;
  status: string;
  quote_amount: string | null;
  scheduled_at: string | null;
};

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
