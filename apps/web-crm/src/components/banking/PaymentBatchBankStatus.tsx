"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { GateStatusNotice } from "@/components/gated/GateStatusNotice";
import { useReleaseGate } from "@/components/gated/useReleaseGate";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Statuswerte, die ohne Buchung erfasst werden. */
export const BATCH_STATUS_CHOICES = ["submitted", "accepted_by_bank", "rejected"] as const;
/** AK16 (GAI-404): "executed" bucht den Ausgleich, "returned" storniert ihn (D06, D38). Beide sind
 *  in der Maske nur bei offener Freigabestufe G2 absendbar; die API prüft weiter selbst. */
export const BOOKING_STATUS_CHOICES = ["executed", "returned"] as const;
type Choice = (typeof BATCH_STATUS_CHOICES)[number] | (typeof BOOKING_STATUS_CHOICES)[number];
const isBooking = (s: Choice) => (BOOKING_STATUS_CHOICES as readonly string[]).includes(s);

/** Gate-Maske nur für buchende Statuswerte, damit die Freigabestufe erst bei Bedarf geladen wird. */
function BookingGate({ onOpen }: { onOpen: (open: boolean) => void }) {
  const t = useTranslations("BankActions.batchStatus");
  const state = useReleaseGate("G2");
  useEffect(() => onOpen(state.status === "open"), [state.status, onOpen]);
  return (
    <div data-testid="batch-bank-status-booking">
      <p className={ui.notice} role="note">
        {t("bookingEffect")}
      </p>
      <p className="text-xs text-muted">{t("fourEyes")}</p>
      <GateStatusNotice gate="G2" state={state} lockedText={t("bookingLocked")} />
    </div>
  );
}

/** Bankrückmeldung je Zahlungsdatei erfassen (GAI-404, D06): Eingereicht, Von der Bank angenommen
 *  oder Abgelehnt (mit Grund). Die Rückmeldung ändert nur den Auftragsstatus; eine Ablehnung lässt
 *  die Verbindlichkeit voll offen (D37). Braucht accounting:approve. */
export function PaymentBatchBankStatus({ batchId, canApprove, onDone }: { batchId: string; canApprove: boolean; onDone?: () => void }) {
  const t = useTranslations("BankActions.batchStatus");
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Choice>("accepted_by_bank");
  const [reason, setReason] = useState("");
  const [txId, setTxId] = useState("");
  const [gateOpen, setGateOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canApprove) return null;
  const booking = isBooking(status);
  const reasonMissing = (status === "rejected" || status === "returned") && reason.trim().length < 3;
  const txMissing = status === "executed" && txId.trim().length === 0;
  const blocked = reasonMissing || txMissing || (booking && !gateOpen);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<unknown[]>(`/api/bff/banking/payment-batches/${batchId}/bank-status`, {
      method: "POST",
      body: JSON.stringify({
        status,
        reason: reason.trim() ? reason.trim() : null,
        ...(booking && txId.trim() ? { bank_transaction_id: txId.trim() } : {}),
      }),
    });
    setBusy(false);
    if (res.ok) {
      setNotice(t("recorded", { count: res.data.length }));
      setOpen(false);
      setReason("");
      setTxId("");
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
              {[...BATCH_STATUS_CHOICES, ...BOOKING_STATUS_CHOICES].map((s) => (
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
          {booking ? (
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("bankTransaction")}</span>
              <input className={ui.input} value={txId} onChange={(e) => setTxId(e.target.value)} />
            </label>
          ) : null}
          <p className="text-xs text-muted">{t("hint")}</p>
          {booking ? <BookingGate onOpen={setGateOpen} /> : null}
          <div className="flex gap-1">
            <button type="button" className={ui.buttonSm} onClick={() => void submit()} disabled={busy || blocked} aria-busy={busy}>
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
