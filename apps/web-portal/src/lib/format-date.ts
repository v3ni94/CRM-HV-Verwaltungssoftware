/** Server safe date formatters (no "use client"): UI format TT.MM.JJJJ, timestamps in
 *  Europe/Berlin (internally ISO 8601, UTC). Pendant to the CRM `lib/format.ts`. */

const dateOnly = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Europe/Berlin" });
const dateTime = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Berlin",
});

/** "2026-09-23" -> "23.09.2026" (no Date conversion); timestamps become the Berlin calendar day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (plain) return `${plain[3]}.${plain[2]}.${plain[1]}`;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateOnly.format(date);
}

/** ISO timestamp -> "23.09.2026, 14:05" in Europe/Berlin. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTime.format(date);
}
