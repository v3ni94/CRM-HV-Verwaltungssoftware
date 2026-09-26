"use client";

import { useTranslations } from "next-intl";

import { SafeLine } from "@/components/ui/SafeText";
import { formatDateTime } from "@/lib/format";

export type TicketEventRow = {
  id?: string;
  kind: string;
  data?: Record<string, unknown> | null;
  at: string;
  user_name?: string | null;
  assignee_name?: string | null;
};

const KNOWN_KINDS = new Set([
  "created",
  "status",
  "assigned",
  "reopened",
  "mail_received",
  "merged_from",
  "merged_into",
  "invoice_attached",
]);

/** Verlauf des Tickets (Review 26.09.2026, M6): jedes Ereignis mit Zeit, Art, Bearbeiter und
 *  den Details aus `data` (Statuswechsel von/nach, Zuweisung an, Grund, Massenaktion). Unbekannte
 *  Arten werden mit ihrem Schlüssel und den Rohdaten gezeigt, nie stillschweigend verkürzt. */
export function TicketHistory({ events }: { events: TicketEventRow[] }) {
  const t = useTranslations("Tickets");
  const statusLabel = (value: unknown) => {
    const key = String(value ?? "");
    return ["new", "in_progress", "waiting", "done", "closed", "rejected"].includes(key) ? t(`statuses.${key}`) : key;
  };
  const details = (e: TicketEventRow): string => {
    const d = e.data ?? {};
    switch (e.kind) {
      case "status":
        return `${statusLabel(d.from)} → ${statusLabel(d.to)}${d.bulk ? ` (${t("events.bulk")})` : ""}`;
      case "assigned": {
        const who = e.assignee_name ?? String(d.to ?? d.user_id ?? "");
        return d.reason ? `${who} (${String(d.reason)})` : who;
      }
      case "created":
        return d.routing ? t(`events.routing.${String(d.routing) === "template" ? "template" : "manual"}`) : "";
      case "merged_from":
      case "merged_into":
        return d.number ? `#${String(d.number)}` : "";
      case "invoice_attached":
        return "";
      default: {
        const entries = Object.entries(d).filter(([, v]) => v !== null && v !== undefined && v !== "");
        return entries.map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(", ");
      }
    }
  };
  if (events.length === 0) return <p className="text-xs text-muted">{t("events.empty")}</p>;
  return (
    <ul className="text-xs text-muted" data-testid="ticket-history">
      {events.map((e, i) => {
        const label = KNOWN_KINDS.has(e.kind) ? t(`events.${e.kind}`) : e.kind;
        const detail = details(e);
        return (
          <li key={e.id ?? i} className="min-w-0">
            <SafeLine>
              {formatDateTime(e.at)} · {label}
              {detail ? `: ${detail}` : ""}
              {e.user_name ? ` · ${t("events.by", { name: e.user_name })}` : ""}
            </SafeLine>
          </li>
        );
      })}
    </ul>
  );
}
