/** Decimal helpers for the Lexware invoice draft form (INT-LEXO-01): amounts travel as
 *  decimal strings, never as float. The control sums mirror `payloads.invoice_totals`
 *  (ROUND_HALF_UP to cents); Lexware Office computes the binding totals. */

const SCALE = 100_000_000n; // eight decimals for intermediate values (6.9.8)

/** "1.234,56", "1234,56" and "1234.56" to the canonical API string "1234.56"; null if invalid. */
export function parseDecimal(input: string, maxFraction = 4): string | null {
  let text = input.trim();
  if (!text) return null;
  if (text.includes(",")) text = text.replace(/\./g, "").replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(text)) return null;
  const [, frac = ""] = text.split(".");
  if (frac.length > maxFraction) return null;
  return text;
}

function scaled(value: string): bigint {
  const negative = value.startsWith("-");
  const [int = "0", frac = ""] = value.replace("-", "").split(".");
  const digits = (frac + "00000000").slice(0, 8);
  const result = BigInt(int) * SCALE + BigInt(digits);
  return negative ? -result : result;
}

/** Round a scaled value to cents (half up, away from zero) and format as "1.234,56 EUR". */
function toCents(value: bigint): bigint {
  const unit = SCALE / 100n;
  const negative = value < 0n;
  const abs = negative ? -value : value;
  const cents = (abs + unit / 2n) / unit;
  return negative ? -cents : cents;
}

export function formatCents(cents: bigint): string {
  const negative = cents < 0n;
  const abs = negative ? -cents : cents;
  const int = (abs / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const frac = (abs % 100n).toString().padStart(2, "0");
  return `${negative ? "-" : ""}${int},${frac} EUR`;
}

export type SumLine = { quantity: string; unit_price: string; tax_rate_percent: 0 | 7 | 19 };

export function localTotals(taxType: "net" | "gross" | "vatfree", lines: SumLine[]): { net: string; tax: string; gross: string } {
  let net = 0n;
  let gross = 0n;
  for (const line of lines) {
    const amount = (scaled(line.unit_price) * scaled(line.quantity)) / SCALE;
    const rate = BigInt(line.tax_rate_percent);
    if (taxType === "gross") {
      gross += amount;
      net += (amount * 100n) / (100n + rate);
    } else {
      net += amount;
      gross += (amount * (100n + rate)) / 100n;
    }
  }
  const netCents = toCents(net);
  const grossCents = toCents(gross);
  return { net: formatCents(netCents), tax: formatCents(grossCents - netCents), gross: formatCents(grossCents) };
}
