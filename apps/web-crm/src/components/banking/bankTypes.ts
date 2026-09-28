/** Shared types of the bank screens (BK-2, plan M12 step S2). They mirror the existing API
 *  payloads of `mhvp.banking.routers` and `mhvp.accounting`; nothing here changes the API. */

export type TransactionStatus = "new" | "proposed" | "needs_review" | "booked" | "ignored" | "split";

export type Transaction = {
  id: string;
  property_bank_account_id: string;
  legal_entity_id: string;
  bank_reference: string | null;
  booking_date: string;
  value_date: string | null;
  amount: string;
  currency: string;
  counterpart_name: string | null;
  counterpart_iban_suffix?: string | null;
  purpose: string | null;
  end_to_end_id: string | null;
  mandate_reference: string | null;
  status: TransactionStatus;
  possible_duplicate_of_id: string | null;
  transfer_pair_id: string | null;
  journal_entry_id: string | null;
};

export type Split = { open_item_id: string; amount: string; contract_id?: string | null };

export type Proposal = {
  source: "rule" | "match" | "ai";
  kind: string;
  confidence: number | null;
  reasoning: string[] | string | null;
  account_number: string | null;
  rule_id?: string | null;
  splits?: Split[];
  unambiguous?: boolean;
};

export type AiProposal = Proposal & {
  id: string;
  decision: string;
  proposed?: { splits?: Split[]; account_number?: string | null } | null;
};

export type Proposals = {
  bank_transaction_id?: string;
  amount?: string;
  ledger_id?: string | null;
  stage1: Proposal[];
  ai: AiProposal[];
  ai_stage: { enabled: boolean; blocked_reason: string | null };
  note: string;
};

/** `GET /accounting/ledgers/{id}/accounts` (AccountOut). */
export type LedgerAccount = {
  id: string;
  number: string;
  name: string;
  category: string;
  type: string;
  active: boolean;
  is_system: boolean;
  property_bank_account_id: string | null;
  review_status?: string;
  vat_option?: string;
};

/** `GET /accounting/ledgers/{id}/open-items?as_of=` (dict rows of `services.open_items`). */
export type OpenItem = {
  id: string;
  account_id: string;
  account_number: string;
  kind: string;
  journal_entry_id: string | null;
  booking_date: string;
  due_date: string | null;
  amount: string;
  remaining: string;
  contract_id: string | null;
};

/** `GET /banking/accounts` (BankAccountListOut), reduced to what the screens need. */
export type BankAccountOption = {
  id: string;
  property_id: string;
  property_number: string | null;
  property_name: string | null;
  legal_entity_id: string;
  legal_entity_name: string | null;
  kind: string;
  iban_masked: string;
  bank_name: string | null;
  holder: string;
};

export type Ledger = { id: string; legal_entity_id: string; name: string };

/** Integer cents from a decimal string or number; NaN and empty input count as 0. */
export function toCents(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(String(value).replace(",", "."));
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

/** Decimal string with two places from integer cents (API amounts are strings). */
export function fromCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/** Contra account candidates of the booking dialog: never the own or another bank account,
 *  never a system account, never an inactive account (operator brief BK-2). */
export function isContraAccountCandidate(account: LedgerAccount): boolean {
  return (
    account.active &&
    !account.is_system &&
    account.property_bank_account_id === null &&
    account.category !== "bank"
  );
}

/** Bank accounts of the ledger other than the own one; the partner side of a transfer pair
 *  is booked against one of them (D04, B08). */
export function isPartnerBankAccountCandidate(account: LedgerAccount, ownBankAccountId: string): boolean {
  return (
    account.active &&
    account.property_bank_account_id !== null &&
    account.property_bank_account_id !== ownBankAccountId
  );
}

export function accountLabel(account: Pick<LedgerAccount, "number" | "name">): string {
  return `${account.number} ${account.name}`;
}

export function bankAccountLabel(account: BankAccountOption): string {
  const property = account.property_number ?? account.property_name ?? "";
  return `${account.iban_masked} ${account.bank_name ?? ""} ${property}`.replace(/\s+/g, " ").trim();
}
