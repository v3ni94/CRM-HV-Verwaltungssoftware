"use client";

import { useTranslations } from "next-intl";

/** Traffic light of the ticket lists (operator 26.09.2026, rule M19-09). The level is derived
 * on the server from the last staff reaction (status change, assignment, staff comment,
 * outbound mail, work order); the CRM only maps it to colours and an accessible text. */
export type Attention = "none" | "new" | "stale_24h" | "stale_96h" | "closed";

export const ATTENTION_LEVELS: Attention[] = ["stale_96h", "stale_24h", "new", "closed"];

/** Left border colour per level: green closed, yellow new, orange 24 h, red 96 h. */
export const ATTENTION_BORDER: Record<Attention, string> = {
  none: "border-l-4 border-l-transparent",
  new: "border-l-4 border-l-yellow-400",
  stale_24h: "border-l-4 border-l-orange-500",
  stale_96h: "border-l-4 border-l-red-600",
  closed: "border-l-4 border-l-emerald-500",
};

const ATTENTION_DOT: Record<Attention, string> = {
  none: "bg-transparent",
  new: "bg-yellow-400",
  stale_24h: "bg-orange-500",
  stale_96h: "bg-red-600",
  closed: "bg-emerald-500",
};

export function asAttention(value: unknown): Attention {
  return value === "new" || value === "stale_24h" || value === "stale_96h" || value === "closed" ? value : "none";
}

/** Whole hours since the reference time, never negative. */
export function hoursSince(iso: string | null | undefined, now: Date = new Date()): number {
  if (!iso) return 0;
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return 0;
  return Math.max(0, Math.floor((now.getTime() - at) / 3_600_000));
}

/** Accessible text such as "Seit 3 Tagen ohne Reaktion"; empty for level none. */
export function useAttentionLabel(): (attention: Attention, lastActivityAt: string | null | undefined) => string {
  const t = useTranslations("Tickets.attention");
  return (attention, lastActivityAt) => {
    if (attention === "none") return "";
    if (attention === "closed") return t("closed");
    if (attention === "new") return t("new");
    const hours = hoursSince(lastActivityAt);
    if (hours >= 48) return t("staleDays", { days: Math.floor(hours / 24) });
    return t("staleHours", { hours });
  };
}

export function AttentionBadge({ attention, lastActivityAt }: { attention: Attention; lastActivityAt: string | null | undefined }) {
  const label = useAttentionLabel()(attention, lastActivityAt);
  if (!label) return null;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" data-testid="attention-label" data-attention={attention}>
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${ATTENTION_DOT[attention]}`} />
      {label}
    </span>
  );
}

/** Legend above a list: what the colours mean. */
export function AttentionLegend() {
  const t = useTranslations("Tickets.attention");
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label={t("legend")} data-testid="attention-legend">
      {ATTENTION_LEVELS.map((level) => (
        <li key={level} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${ATTENTION_DOT[level]}`} />
          {t(`legend_${level}`)}
        </li>
      ))}
    </ul>
  );
}
