"use client";

import { useTranslations } from "next-intl";

/** Traffic light of the ticket lists (operator 26.09.2026, rule M19-09). The level is derived
 * on the server from the last staff reaction (status change, assignment, staff comment,
 * outbound mail, work order); the CRM only maps it to colours and an accessible text.
 * Types and pure helpers (asAttention, hoursSince, ATTENTION_BORDER) live in ./attention.ts so
 * that server components can call them; this file holds the client components only. */
import { ATTENTION_DOT, ATTENTION_LEVELS, hoursSince, type Attention } from "@/components/tickets/attention";

export type { Attention } from "@/components/tickets/attention";

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
