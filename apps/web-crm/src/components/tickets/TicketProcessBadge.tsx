"use client";

import { useTranslations } from "next-intl";

import { StatusPill } from "@/components/ui/StatusPill";

/** Fixed process catalogue of rule M19-11 (mirrors `mhvp.tickets.flows.PROCESS_CODES`). */
export const PROCESS_CODES = [
  "kuendigung",
  "vermietung",
  "versicherungsschaden",
  "reparaturanfrage",
  "beschwerde",
  "buchhaltung",
  "uebergabe",
  "mieterhoehung",
  "gericht",
  "objektuebernahme",
  "objektabgabe",
  "kaution",
] as const;
export type ProcessCode = (typeof PROCESS_CODES)[number];

export function isProcessCode(value: unknown): value is ProcessCode {
  return typeof value === "string" && (PROCESS_CODES as readonly string[]).includes(value);
}

/** Badge of the process category on a ticket (list, detail, mail suggestion). The label
 *  comes from the catalogue translations; an unknown code shows the code itself. */
export function TicketProcessBadge({
  code,
  confidence,
  className = "",
}: {
  code: string | null | undefined;
  confidence?: number | null;
  className?: string;
}) {
  const t = useTranslations("Tickets.process");
  if (!code) return null;
  const label = isProcessCode(code) ? t(`codes.${code}`) : code;
  const suffix = typeof confidence === "number" ? ` (${Math.round(confidence * 100)}%)` : "";
  return (
    <span data-testid="ticket-process-badge" data-process={code} className={className}>
      <StatusPill variant="gold" label={`${label}${suffix}`} />
    </span>
  );
}
