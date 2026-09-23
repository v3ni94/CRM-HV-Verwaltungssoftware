/** UI formats: dates TT.MM.JJJJ, timestamps in Europe/Berlin (internally ISO 8601, UTC). */

const dateTime = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Berlin",
});

const dateOnly = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "Europe/Berlin",
});

/** "2026-09-23" -> "23.09.2026"; ISO timestamps are converted to the Berlin calendar day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (plain) return `${plain[3]}.${plain[2]}.${plain[1]}`;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateOnly.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTime.format(date).replace(",", "");
}

/**
 * Decimal string from the API ("1234.5", "-0.125") -> "1.234,50 EUR". Works on the string
 * (no float for money, 6.9.8); rounds half up to two decimals.
 */
export function formatEur(value: string | number | null | undefined): string {
  const amount = formatDecimal(value, 2);
  return amount ? `${amount} EUR` : "";
}

/** Decimal string -> German notation with the given number of decimals, without float. */
export function formatDecimal(value: string | number | null | undefined, decimals: number): string {
  if (value === null || value === undefined || value === "") return "";
  const match = /^(-?)(\d*)(?:\.(\d*))?$/.exec(String(value).trim());
  if (!match) return String(value);
  const negative = match[1] === "-";
  let digits = (match[2] || "0") + (match[3] ?? "").padEnd(decimals + 1, "0").slice(0, decimals + 1);
  // Round half up on the last extra digit.
  const roundUp = Number(digits.slice(-1)) >= 5;
  digits = digits.slice(0, -1);
  if (roundUp) {
    const chars = digits.split("");
    let i = chars.length - 1;
    for (; i >= 0; i -= 1) {
      if (chars[i] === "9") chars[i] = "0";
      else {
        chars[i] = String(Number(chars[i]) + 1);
        break;
      }
    }
    digits = (i < 0 ? "1" : "") + chars.join("");
  }
  const intPart = digits.slice(0, digits.length - decimals).replace(/^0+(?=\d)/, "") || "0";
  const fracPart = decimals > 0 ? digits.slice(digits.length - decimals) : "";
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const isZero = /^[0.]*$/.test(intPart + fracPart);
  return `${negative && !isZero ? "-" : ""}${grouped}${fracPart ? `,${fracPart}` : ""}`;
}

/** Confidence 0..1 (decimal string or number) -> "87 %". */
export function formatConfidence(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n * 100)} %` : "";
}
