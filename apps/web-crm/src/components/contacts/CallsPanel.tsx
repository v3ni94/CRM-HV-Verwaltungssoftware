"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Anrufliste am Kontakt (13.5, A70): Anrufnotizen aus dem Telefonie-Webhook, ohne
 *  Gesprächsinhalte. Ein Vorschlag "Rückruf" wird erst durch eine Person zum Ticket. */
export type CallOut = {
  id: string;
  event: "started" | "ended" | "missed";
  direction: "inbound" | "outbound";
  number: string;
  number_masked: boolean;
  started_at: string;
  duration_seconds: number | null;
  contact_id: string | null;
  contact_name: string | null;
  match_status: "matched" | "ambiguous" | "unknown";
  related_ticket_id: string | null;
  proposal_status: "none" | "proposed" | "accepted" | "dismissed";
  ticket_id: string | null;
  note: string | null;
};

function duration(seconds: number | null): string {
  if (seconds === null) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function CallsPanel({ calls, canCreateTicket }: { calls: CallOut[]; canCreateTicket: boolean }) {
  const t = useTranslations("Calls");
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Record<string, number>>({});

  async function decide(call: CallOut, action: "accept" | "dismiss") {
    setBusy(call.id);
    setError(null);
    const res = await bff<{ number?: number }>(`/api/bff/communication/calls/${call.id}/proposal/${action}`, {
      method: "POST",
      ...(action === "accept" ? { body: JSON.stringify({}) } : {}),
    });
    setBusy(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    if (action === "accept" && res.data?.number) setCreated((c) => ({ ...c, [call.id]: res.data.number as number }));
    router.refresh();
  }

  if (!calls.length) return <p className="text-sm text-muted">{t("none")}</p>;
  return (
    <div className="flex flex-col gap-2">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {calls.map((call) => (
          <li key={call.id} className={ui.card}>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className={call.event === "missed" ? ui.badgeWarning : ui.badge}>
                {t(`event.${call.event}`)}
              </span>
              <span className="text-xs text-muted">{t(`direction.${call.direction}`)}</span>
              <span className="font-mono">{call.number}</span>
              {call.number_masked ? <span className="text-xs text-muted">{t("masked")}</span> : null}
              <span className="text-xs text-muted">{formatDateTime(call.started_at)}</span>
              {call.duration_seconds !== null ? (
                <span className="text-xs text-muted">{t("duration", { value: duration(call.duration_seconds) })}</span>
              ) : null}
            </div>
            {call.note ? <p className="mt-1 whitespace-pre-wrap text-sm">{call.note}</p> : null}
            {created[call.id] !== undefined ? (
              <p className="mt-1 text-xs text-muted">{t("proposal.created", { number: created[call.id] ?? 0 })}</p>
            ) : null}
            {call.proposal_status === "proposed" && created[call.id] === undefined ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={ui.badgeGold}>{t("proposal.callback")}</span>
                {canCreateTicket ? (
                  <button type="button" className={ui.buttonSm} disabled={busy === call.id} onClick={() => void decide(call, "accept")}>
                    {t("proposal.accept")}
                  </button>
                ) : null}
                <button type="button" className={ui.buttonSm} disabled={busy === call.id} onClick={() => void decide(call, "dismiss")}>
                  {t("proposal.dismiss")}
                </button>
              </div>
            ) : null}
            {call.proposal_status === "accepted" && created[call.id] === undefined ? (
              <p className="mt-1 text-xs text-muted">{t("proposal.accepted")}</p>
            ) : null}
            {call.proposal_status === "dismissed" ? <p className="mt-1 text-xs text-muted">{t("proposal.dismissed")}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
