"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { type AppointmentProposal, formatDateTime } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** A58: Terminvorschläge des Handwerkers zur eigenen Meldung. Der betroffene Bewohner wählt
 *  einen Termin; die Bestätigung setzt den Termin am Auftrag (Ereignis in der Verwaltung). */
export function AppointmentProposals({ proposals }: { proposals: AppointmentProposal[] }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState<string | null>(null);

  if (proposals.length === 0) return null;
  const confirmed = proposals.find((p) => p.status === "accepted");
  const open = proposals.filter((p) => p.status === "proposed");

  async function accept(proposal: AppointmentProposal) {
    setError(null);
    setBusy(true);
    const result = await bff(
      `/api/bff/portal/work-orders/${proposal.work_order_id}/appointment-proposals/${proposal.id}/accept`,
      { method: "POST", body: "{}" },
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setAccepted(proposal.id);
    router.refresh();
  }

  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("appointments")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {accepted ? <p className={ui.success}>{t("appointmentAccepted")}</p> : null}
      {confirmed ? (
        <p className="text-sm">
          <span className="font-medium">{t("appointmentConfirmed")}:</span> {formatDateTime(confirmed.starts_at)}
        </p>
      ) : null}
      {open.length > 0 && !accepted ? (
        <>
          <p className={ui.help}>{t("appointmentsHint")}</p>
          <ul className="flex flex-col gap-2">
            {open.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm">
                <span>
                  <span className="font-medium">{formatDateTime(p.starts_at)}</span>
                  {p.note ? <span className="text-muted"> ({p.note})</span> : null}
                </span>
                <button type="button" className={ui.button} disabled={busy} onClick={() => void accept(p)}>
                  {t("appointmentAccept")}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
