"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Bankbewegung als unbelegt melden (GAI-406, Regel B05): eine Person eröffnet die Klärungszeile mit
 *  Begründung; ab dann braucht die Buchung den Beleg oder eine begründete Entscheidung "Kein Beleg
 *  erforderlich". Die Meldung bucht nichts. Braucht accounting:update. */
export function ClarificationOpenButton({ txId, onOpened }: { txId: string; onOpened?: () => void }) {
  const t = useTranslations("BankActions.clarification");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/banking/transactions/${txId}/clarification`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    setBusy(false);
    if (res.ok) {
      setDone(true);
      setOpen(false);
      onOpened?.();
    } else setError(res.message);
  };

  if (done) return <span className="text-xs text-muted">{t("opened")}</span>;
  return (
    <span data-testid="clarification-open">
      {!open ? (
        <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
          {t("open")}
        </button>
      ) : (
        <span className="flex flex-wrap items-center gap-1">
          <input aria-label={t("reason")} placeholder={t("reason")} className={ui.input} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="button" className={ui.buttonSm} onClick={() => void submit()} disabled={busy || reason.trim().length < 3}>
            {t("submit")}
          </button>
          <button type="button" className={ui.buttonSm} onClick={() => setOpen(false)}>
            {t("cancel")}
          </button>
        </span>
      )}
      {error ? (
        <span role="alert" className={`${ui.alert} block`}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
