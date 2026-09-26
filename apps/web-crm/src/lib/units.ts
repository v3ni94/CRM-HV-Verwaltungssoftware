/**
 * Unit numbers (Betreiberauftrag 26.09.2026): natural order "1" < "2" < "10", "WE1" < "WE2" < "WE10".
 * Numbers stay as stored; padding with leading zeros is display only.
 */
const CHUNK = /(\d+)/;

export function naturalCompare(a: string, b: string): number {
  const pa = a.trim().split(CHUNK).filter((p) => p !== "");
  const pb = b.trim().split(CHUNK).filter((p) => p !== "");
  for (let i = 0; i < Math.min(pa.length, pb.length); i += 1) {
    const x = pa[i] ?? "";
    const y = pb[i] ?? "";
    const nx = /^\d+$/.test(x);
    const ny = /^\d+$/.test(y);
    if (nx && ny) {
      const d = Number(x) - Number(y);
      if (d !== 0) return d;
    } else if (nx !== ny) {
      return nx ? -1 : 1;
    } else {
      const d = x.localeCompare(y, "de", { sensitivity: "base" });
      if (d !== 0) return d;
    }
  }
  if (pa.length !== pb.length) return pa.length - pb.length;
  return a.localeCompare(b, "de");
}

export function sortUnits<T extends { number: string }>(units: readonly T[]): T[] {
  return [...units].sort((a, b) => naturalCompare(a.number, b.number));
}

/** Display formatter: pads to three digits only when every number of the property is purely numeric. */
export function unitNumberFormatter(numbers: readonly string[]): (n: string) => string {
  const allNumeric = numbers.length > 0 && numbers.every((n) => /^\d+$/.test(n.trim()));
  if (!allNumeric) return (n) => n;
  const width = Math.max(3, ...numbers.map((n) => String(Number(n)).length));
  return (n) => String(Number(n)).padStart(width, "0");
}

/** Quantity from the API ("65.50000000") -> "65,5"; no float, trailing zeros removed. */
export function formatQty(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const text = String(value).trim();
  const match = /^(-?)(\d+)(?:\.(\d*))?$/.exec(text);
  if (!match) return text;
  const intPart = (match[2] ?? "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const frac = (match[3] ?? "").replace(/0+$/, "");
  return `${match[1]}${intPart}${frac ? `,${frac}` : ""}`;
}

type Named = { party_name: string; members?: { display_name: string }[] | null };

/** Occupant name for display: member names when present, else the party name. */
export function occupantName(o: Named): string {
  const names = (o.members ?? []).map((m) => m.display_name);
  return names.length ? names.join(", ") : o.party_name;
}
