/** Server safe amount formatter (no "use client"): shared by server pages and client components.
 *  Works on the decimal string of the API without float arithmetic (rule 6.9.8) and rounds half
 *  up away from zero, like the CRM helper `formatDecimal`. */

/** Decimal string ("1234.5", "-0.125") or number -> German notation with `decimals` places. */
export function formatDecimal(value: string | number, decimals = 2): string {
  const raw = String(value).trim();
  const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(raw);
  if (!match || (match[2] === "" && !match[3])) {
    // Exponent notation or other input: fall back to Number, never throw.
    const n = Number(raw);
    return Number.isFinite(n)
      ? new Intl.NumberFormat("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n)
      : raw;
  }
  const negative = match[1] === "-";
  const whole = match[2] || "0";
  const fraction = match[3] ?? "";
  let digits = BigInt(whole + fraction.padEnd(decimals + 1, "0").slice(0, decimals + 1));
  if (digits % 10n >= 5n) digits += 10n;
  digits /= 10n;
  const text = digits.toString().padStart(decimals + 1, "0");
  const intPart = text.slice(0, text.length - decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const fracPart = decimals > 0 ? `,${text.slice(text.length - decimals)}` : "";
  return `${negative && digits !== 0n ? "-" : ""}${intPart}${fracPart}`;
}

/** "1234.5" -> "1.234,50" (without currency). */
export function formatAmount(value: string | number): string {
  return formatDecimal(value, 2);
}

/** "1234.5" -> "1.234,50 EUR". */
export function formatEur(value: string | number): string {
  return `${formatAmount(value)} EUR`;
}

/** Amount strings to integer cents (string based, half up) for running balances. */
export function toCents(value: string): bigint {
  return BigInt(formatDecimal(value, 2).replace(/\./g, "").replace(",", ""));
}

/** Integer cents -> decimal string with two places ("-1234" -> "-12.34"). */
export function fromCents(cents: bigint): string {
  const negative = cents < 0n;
  const text = (negative ? -cents : cents).toString().padStart(3, "0");
  return `${negative ? "-" : ""}${text.slice(0, -2)}.${text.slice(-2)}`;
}
