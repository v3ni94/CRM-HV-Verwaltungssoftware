/**
 * Sollbeträge eines Vertrags (contract_payment, spec 6.3): pure helpers for the amounts
 * section. Money stays a decimal string; sums and the gross computation use integer cents
 * (BigInt), never float (6.9.8).
 */

/** Row of GET /contracts/{id}/payments (PaymentOut). */
export type AmountRow = {
  id: string;
  contract_id: string;
  payment_type_code: string;
  net: string;
  vat_percent: string;
  gross: string;
  currency: string;
  valid_from: string;
  valid_to: string | null;
  reason: AmountReason;
};

export type AmountReason = "initial" | "index" | "graduated" | "increase" | "adjustment_from_statement" | "other";

export const AMOUNT_REASONS: AmountReason[] = ["initial", "increase", "index", "graduated", "adjustment_from_statement", "other"];

/** Entry of the tenant catalogue `payment_type` (GET /catalogs/payment_type). */
export type PaymentTypeOption = { code: string; label: string };

/** Candidate for a new amount: the period the operator wants to record. */
export type AmountPeriod = { payment_type_code: string; valid_from: string; valid_to: string | null };

/** "1.234,56" or "1234,56" or "1234.56" -> "1234.56" (string, no float); null when invalid.
 *  A leading minus is accepted only with `allowNegative` (Mietminderung). */
export function parseAmount(input: string, options: { allowNegative?: boolean } = {}): string | null {
  let raw = input.trim().replace(/\s|EUR|€/g, "");
  let sign = "";
  if (raw.startsWith("-")) {
    if (!options.allowNegative) return null;
    sign = "-";
    raw = raw.slice(1);
  }
  if (!raw) return null;
  let normalised: string;
  if (raw.includes(",")) normalised = raw.replace(/\./g, "").replace(",", ".");
  else if (/^\d+\.\d{1,2}$/.test(raw)) normalised = raw;
  else normalised = raw.replace(/\./g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return null;
  const [int, frac = ""] = normalised.split(".");
  return `${sign}${int}.${frac.padEnd(2, "0")}`;
}

const CENTS = /^(-?)(\d+)(?:\.(\d{1,2}))?$/;

/** "1234.5" -> 123450n (cents). Throws on anything that is not a plain decimal string. */
export function toCents(value: string): bigint {
  const match = CENTS.exec(value.trim());
  if (!match) throw new Error(`invalid amount: ${value}`);
  const cents = BigInt(match[2]!) * 100n + BigInt((match[3] ?? "").padEnd(2, "0"));
  return match[1] === "-" ? -cents : cents;
}

/** 123450n -> "1234.50" (decimal string for the API and formatEur). */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  const int = abs / 100n;
  const frac = (abs % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${int}.${frac}`;
}

/** Gross from net and VAT percent (up to 8 decimals), rounded half up to cents, no float.
 *  Mirrors `contracts.services.check_amounts`: gross = net * (1 + vat / 100). */
export function grossFromNet(net: string, vatPercent: string): string {
  const netCents = toCents(net);
  const vat = /^(\d+)(?:\.(\d{1,8}))?$/.exec(vatPercent.trim().replace(",", "."));
  if (!vat) throw new Error(`invalid vat percent: ${vatPercent}`);
  const SCALE = 100_000_000n; // 8 decimals of the percentage
  const vatScaled = BigInt(vat[1]!) * SCALE + BigInt((vat[2] ?? "").padEnd(8, "0"));
  const numerator = netCents * (100n * SCALE + vatScaled);
  const denominator = 100n * SCALE;
  return fromCents(divideHalfUp(numerator, denominator));
}

function divideHalfUp(numerator: bigint, denominator: bigint): bigint {
  const negative = numerator < 0n;
  const abs = negative ? -numerator : numerator;
  const quotient = (abs * 2n + denominator) / (2n * denominator);
  return negative ? -quotient : quotient;
}

/** Rows whose period (inclusive, open end = null) contains the given ISO date. */
export function amountsValidOn<T extends { valid_from: string; valid_to: string | null }>(rows: T[], isoDate: string): T[] {
  return rows.filter((r) => r.valid_from <= isoDate && (r.valid_to === null || r.valid_to >= isoDate));
}

/** Sum of the gross amounts valid on the date as decimal string ("0.00" without rows). */
export function monthlyTotal(rows: AmountRow[], isoDate: string): string {
  return fromCents(amountsValidOn(rows, isoDate).reduce((sum, r) => sum + toCents(r.gross), 0n));
}

/** Both periods share at least one day (inclusive bounds, null = open end). */
export function periodsOverlap(a: { valid_from: string; valid_to: string | null }, b: { valid_from: string; valid_to: string | null }): boolean {
  const aEnd = a.valid_to ?? "9999-12-31";
  const bEnd = b.valid_to ?? "9999-12-31";
  return a.valid_from <= bEnd && b.valid_from <= aEnd;
}

/**
 * Row of the same kind the new amount would overlap. An open row that starts before the new
 * one is not a conflict: the API closes it the day before the new amount (history kept).
 * Returns null when the new amount fits.
 */
export function findOverlap(rows: AmountRow[], candidate: AmountPeriod): AmountRow | null {
  for (const row of rows) {
    if (row.payment_type_code !== candidate.payment_type_code) continue;
    if (row.valid_to === null && row.valid_from < candidate.valid_from) continue;
    if (periodsOverlap(row, candidate)) return row;
  }
  return null;
}

/** Applies the server rule to the local list after a successful POST: the open predecessor of
 *  the same kind and contract version ends the day before the new amount. */
export function withNewAmount(rows: AmountRow[], created: AmountRow): AmountRow[] {
  const closed = rows.map((r) =>
    r.contract_id === created.contract_id && r.payment_type_code === created.payment_type_code && r.valid_to === null && r.valid_from < created.valid_from
      ? { ...r, valid_to: previousDay(created.valid_from) }
      : r,
  );
  return sortAmounts([...closed, created]);
}

export function sortAmounts(rows: AmountRow[]): AmountRow[] {
  return [...rows].sort((a, b) => a.payment_type_code.localeCompare(b.payment_type_code) || a.valid_from.localeCompare(b.valid_from));
}

export function previousDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}
