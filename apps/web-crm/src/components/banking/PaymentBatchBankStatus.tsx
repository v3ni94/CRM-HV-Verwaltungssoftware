"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Statuswerte, die ohne Buchung erfasst werden. "executed" und "returned" lösen Buchungen aus
 *  (Ausgleich, Storno) und laufen weiter über den Import der Bankrückmeldung (pain.002, camt.054)
 *  beziehungsweise die API, bis G1 und G2 offen sind. */
export const BATCH_STATUS_CHOICES = ["submitted", "accepted_by_bank", "rejected"] as const;
type Choice = (typeof BATCH_STATUS_CHOICES)[number];

/** Bankrückmeldung je Zahlungsdatei erfassen (GAI-404, D06): Eingereicht, Von der Bank angenommen
 *  oder Abgelehnt (mit Grund). Die Rückmeldung ändert nur den Auftragsstatus; eine Ablehnung lässt
 *  die Verbindlichkeit voll offen (D37). Braucht accounting:approve. */
export function PaymentBatchBankStatus({ batchId, canApprove, onDone }: { batchId: string; canApprove: boolean; onDone?: () => void }) {
  const t = useTranslations("BankActions.batchStatus");
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Choice>("accepted_by_bank");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canApprove) return null;
  const reasonMissing = status === "rejected" && reason.trim().length < 3;

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<unknown[]>(`/api/bff/banking/payment-batches/${batchId}/bank-status`, {
      method: "POST",
      body: JSON.stringify({ status, reason: reason.trim() ? reason.trim() : null }),
    });
    setBusy(false);
    if (res.ok) {
      setNotice(t("recorded", { count: res.data.length }));
      setOpen(false);
      setReason("");
      onDone?.();
    } else setError(res.message);
  };

  return (
    <div data-testid="batch-bank-status">
      {!open ? (
        <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
          {t("open")}
        </button>
      ) : (
        <div className="flex flex-col gap-1">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("status")}</span>
            <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value as Choice)}>
              {BATCH_STATUS_CHOICES.map((s) => (
                <option key={s} value={s}>
                  {t(`status_${s}` as "status_submitted")}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reason")}</span>
            <input className={ui.input} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <p className="text-xs text-muted">{t("hint")}</p>
          <div className="flex gap-1">
            <button type="button" className={ui.buttonSm} onClick={() => void submit()} disabled={busy || reasonMissing}>
              {t("record")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => setOpen(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-xs text-success-fg">{notice}</p> : null}
    </div>
  );
}
