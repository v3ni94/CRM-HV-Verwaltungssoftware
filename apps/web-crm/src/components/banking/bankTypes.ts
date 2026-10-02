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
  /** Object period lock of the settled items (API field; locked bookings fail with MHVP-ACC-0030). */
  object_period_lock?: { locked: boolean; code: string | null };
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

/** Amount input as the API decimal string with two places, or null when not readable.
 *  Accepts the displayed German notation ("1.250,00", "-12,5"), plain German ("1250,00"),
 *  the API notation ("1250.00", "-79.90") and a dot grouped integer without comma ("1.250").
 *  With both separators the last one is the decimal separator; more than two decimals,
 *  letters or a second decimal separator are not readable. Built from the digit strings,
 *  never through a float. */
export function parseAmount(input: string | null | undefined): string | null {
  if (input === null || input === undefined) return null;
  let s = String(input).trim();
  if (s === "") return null;
  const lastComma = s.lastIndexOf(",");
  const lastDot = s.lastIndexOf(".");
  if (lastComma >= 0 && lastDot >= 0) {
    s = lastComma > lastDot ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  } else if (lastComma >= 0) {
    s = s.replace(",", ".");
  } else if (lastDot >= 0 && /^[+-]?\d{1,3}(\.\d{3})+$/.test(s)) {
    s = s.replace(/\./g, "");
  }
  const m = /^([+-])?(\d+)(?:\.(\d{1,2}))?$/.exec(s);
  if (!m) return null;
  const sign = m[1] === "-" ? "-" : "";
  const whole = m[2]!.replace(/^0+(?=\d)/, "");
  const fraction = (m[3] ?? "").padEnd(2, "0");
  if (whole === "0" && fraction === "00") return "0.00";
  return `${sign}${whole}.${fraction}`;
}

/** Integer cents from an amount string or number; unreadable and empty input count as 0. */
export function toCents(value: string | number | null | undefined): number {
  if (typeof value === "number") return Number.isFinite(value) ? Math.round(value * 100) : 0;
  const parsed = parseAmount(value);
  if (parsed === null) return 0;
  const negative = parsed.startsWith("-");
  const [whole, fraction] = (negative ? parsed.slice(1) : parsed).split(".");
  const cents = Number(whole) * 100 + Number(fraction);
  return negative ? -cents : cents;
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
