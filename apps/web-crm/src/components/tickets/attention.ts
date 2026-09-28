/**
 * Pure helpers and types of the ticket traffic light (operator 26.09.2026, rule M19-09).
 *
 * This module carries no "use client" directive on purpose: server components such as
 * app/(app)/tickets/page.tsx call `asAttention` while mapping the API rows. Functions
 * exported from a "use client" module are client references on the server and throw
 * "Attempted to call asAttention() from the server" in the production build (incident
 * 27.09.2026, /tickets). The React components live in TicketAttention.tsx.
 */

export type Attention = "none" | "new" | "stale_24h" | "stale_96h" | "closed";

export const ATTENTION_LEVELS: Attention[] = ["stale_96h", "stale_24h", "new", "closed"];

/** Left border colour per level: green closed, yellow new, orange 24 h, red 96 h. Colours are
 *  the signal tokens of @mhvp/ui (tuned per day and evening mode), never palette classes. */
export const ATTENTION_BORDER: Record<Attention, string> = {
  none: "border-l-4 border-l-transparent",
  new: "border-l-4 border-l-signal-attention",
  stale_24h: "border-l-4 border-l-signal-warning",
  stale_96h: "border-l-4 border-l-signal-critical",
  closed: "border-l-4 border-l-signal-ok",
};

export const ATTENTION_DOT: Record<Attention, string> = {
  none: "bg-transparent",
  new: "bg-signal-attention",
  stale_24h: "bg-signal-warning",
  stale_96h: "bg-signal-critical",
  closed: "bg-signal-ok",
};

/** Unknown or missing values (old tickets, other API versions) map to "none". */
export function asAttention(value: unknown): Attention {
  return value === "new" || value === "stale_24h" || value === "stale_96h" || value === "closed" ? value : "none";
}

/** Whole hours since the reference time, never negative; 0 for missing or invalid input. */
export function hoursSince(iso: string | null | undefined, now: Date = new Date()): number {
  if (!iso) return 0;
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return 0;
  return Math.max(0, Math.floor((now.getTime() - at) / 3_600_000));
}
