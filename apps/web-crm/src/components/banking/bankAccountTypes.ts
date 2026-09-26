/** Shapes of GET /banking/accounts and GET /properties/{id}/bank-account-options
 *  (Bankkontenauswahl). Read only plus assignment; no payment (G2). */

export type AccountPurpose = "hausgeld" | "miete" | "general";

export type RecentTransaction = {
  id: string;
  booking_date: string;
  amount: string;
  counterpart_name: string | null;
  purpose: string | null;
};

export type AccountAssignment = {
  property_id: string;
  property_number: string | null;
  property_name: string | null;
  purpose: AccountPurpose;
  is_default: boolean;
};

export type BankAccountOption = {
  id: string;
  property_id: string;
  property_number: string | null;
  property_name: string | null;
  legal_entity_id: string;
  legal_entity_name: string | null;
  legal_entity_kind: string | null;
  kind: string;
  iban_masked: string;
  bic: string | null;
  bank_name: string | null;
  holder: string;
  valid_from: string;
  valid_to: string | null;
  source: "finapi" | "manual";
  balance: string | null;
  balance_as_of: string | null;
  balance_source: "finapi" | "statement" | null;
  default_for_legal_entity: boolean;
  assignments: AccountAssignment[];
  recent_transactions: RecentTransaction[];
};

export function accountLabel(a: BankAccountOption): string {
  const bank = a.bank_name ? `, ${a.bank_name}` : "";
  return `${a.holder}${bank} (${a.iban_masked})`;
}

export function accountMatches(a: BankAccountOption, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const hay = [
    a.holder,
    a.bank_name ?? "",
    a.iban_masked,
    a.property_number ?? "",
    a.property_name ?? "",
    a.legal_entity_name ?? "",
    ...a.assignments.map((x) => `${x.property_number ?? ""} ${x.property_name ?? ""}`),
  ]
    .join(" ")
    .toLowerCase();
  return q.split(/\s+/).every((part) => hay.includes(part));
}

export function accountsUrl(filter: { propertyId?: string | null; legalEntityId?: string | null; q?: string }): string {
  const params = new URLSearchParams();
  if (filter.propertyId) params.set("property_id", filter.propertyId);
  if (filter.legalEntityId) params.set("legal_entity_id", filter.legalEntityId);
  if (filter.q) params.set("q", filter.q);
  const qs = params.toString();
  return `/api/bff/banking/accounts${qs ? `?${qs}` : ""}`;
}

export function propertyAccountsUrl(propertyId: string, legalEntityId?: string | null): string {
  const params = new URLSearchParams();
  if (legalEntityId) params.set("legal_entity_id", legalEntityId);
  const qs = params.toString();
  return `/api/bff/properties/${propertyId}/bank-account-options${qs ? `?${qs}` : ""}`;
}
