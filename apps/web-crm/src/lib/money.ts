/**
 * Money arithmetic in integer cents (GAI-114, 4.1, 6.9.8). Decimal strings from the API or from
 * form fields are parsed without going through a binary float; rounding is half up
 * (commercial rounding, away from zero for negative amounts). Previews only: the API remains
 * the source of truth for booked amounts.
 */

/** Parses "1.234,56", "1234.56", "-0,5", "1,005" into integer cents (half up); null if invalid. */
export function parseCents(value: string | number | null | undefined): bigint | null {
  if (value === null || value === undefined) return null;
  let text = typeof value === "number" ? (Number.isFinite(value) ? String(value) : "") : value.trim();
  if (text === "") return null;
  // German format with thousands dots, otherwise a plain decimal point.
  if (/^[+-]?\d{1,3}(\.\d{3})*(,\d+)?$/.test(text) && (text.includes(",") || /\.\d{3}\./.test(text))) {
    text = text.replace(/\./g, "").replace(",", ".");
  } else if (/^[+-]?\d*,\d+$/.test(text)) {
    text = text.replace(",", ".");
  }
  const m = /^([+-])?(\d*)(?:\.(\d+))?$/.exec(text);
  if (!m || (m[2] === "" && m[3] === undefined)) return null;
  const negative = m[1] === "-";
  const whole = BigInt(m[2] || "0");
  const fraction = m[3] ?? "";
  let cents = whole * 100n + BigInt((fraction + "00").slice(0, 2));
  if (fraction.length > 2 && fraction.charCodeAt(2) >= 53) cents += 1n; // third digit >= 5: half up
  return negative ? -cents : cents;
}

/** Integer cents to the API decimal string "-12.30". */
export function centsToDecimal(cents: bigint): string {
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  const text = `${abs / 100n}.${String(abs % 100n).padStart(2, "0")}`;
  return negative ? `-${text}` : text;
}

/** Sum of amounts in cents; null when any value is not a valid amount. */
export function sumCents(values: Array<string | number | null | undefined>): bigint | null {
  let total = 0n;
  for (const v of values) {
    const c = parseCents(v);
    if (c === null) return null;
    total += c;
  }
  return total;
}

/** Warm rent preview: cold rent + additional costs (+ heating unless included); "1234,50" or null. */
export function warmRentDisplay(
  price: string,
  additional: string,
  heating: string,
  heatingIncluded: boolean,
): string | null {
  const p = parseCents(price);
  const a = additional.trim() === "" ? 0n : parseCents(additional);
  const h = heating.trim() === "" ? 0n : parseCents(heating);
  if (p === null || a === null || h === null) return null;
  return centsToDecimal(heatingIncluded ? p + a : p + a + h).replace(".", ",");
}

/** Amount of a booking that can be settled: min(|payment|, sum of the splits), as decimal string. */
export function settleAmount(paymentAmount: string, splitAmounts: string[]): string {
  const total = sumCents(splitAmounts) ?? 0n;
  const pay = parseCents(paymentAmount) ?? 0n;
  const abs = pay < 0n ? -pay : pay;
  return centsToDecimal(abs < total ? abs : total);
}

/** Sum of percentage shares as a decimal number of cents-of-percent precision (1/100 percent
 *  is not enough, shares have up to 8 decimals), computed on scaled integers. */
export function sumShares(values: Array<string | null | undefined>): number {
  const scale = 100_000_000n;
  let total = 0n;
  for (const v of values) {
    const text = (v ?? "").trim().replace(",", ".");
    const m = /^(\d*)(?:\.(\d+))?$/.exec(text);
    if (!m || (m[1] === "" && m[2] === undefined)) continue;
    total += BigInt(m[1] || "0") * scale + BigInt(((m[2] ?? "") + "00000000").slice(0, 8));
  }
  return Number(total) / Number(scale);
}
