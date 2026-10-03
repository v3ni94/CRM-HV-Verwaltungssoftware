"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { GatedAction } from "@/components/gated/GatedAction";
import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ExecutionOrder = {
  id: string;
  counterpart_name: string;
  amount: string | number;
  executed_amount?: string | number | null;
  status: string;
  batch_id?: string | null;
};

const OPEN_STATES = ["exported", "submitted", "accepted_by_bank"];
const toCents = (v: string | number | null | undefined) => Math.round(Number(v ?? 0) * 100);

/** Teilausführung je Auftrag (GAM-203, D37): Ausführung mit Bankumsatz als Nachweis oder
 *  Ablehnung mit Grund, je Auftrag einer Zahlungsdatei. Der ausgeführte Betrag stammt aus der
 *  Belastung des Bankumsatzes, nicht aus einer Eingabe: nur der bestätigte Betrag gleicht die
 *  Verbindlichkeit aus, der Rest bleibt offen. Buchende Wirkung nur bei offener Freigabestufe G2. */
export function PaymentOrderExecution({ orders, canApprove }: { orders: ExecutionOrder[]; canApprove: boolean }) {
  const t = useTranslations("BankActions.execution");
  const router = useRouter();
  const [txIds, setTxIds] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  if (!canApprove || orders.length === 0) return null;

  const reject = async (id: string) => {
    setBusy(id);
    setErrors((e) => ({ ...e, [id]: "" }));
    const res = await bff(`/api/bff/banking/payment-batches/${orders.find((o) => o.id === id)?.batch_id}/bank-status`, {
      method: "POST",
      body: JSON.stringify({ status: "rejected", reason: reasons[id]?.trim(), order_ids: [id] }),
    });
    setBusy(null);
    if (res.ok) router.refresh();
    else setErrors((e) => ({ ...e, [id]: res.message }));
  };
  return (
    <div className="flex flex-col gap-2" data-testid="order-execution">
      <p className="text-xs text-muted">{t("hint")}</p>
      <ul className="flex flex-col gap-2">
        {orders.map((o) => {
          const o2 = o;
          const paid = toCents(o.executed_amount);
          const rest = toCents(o.amount) - paid;
          const open = OPEN_STATES.includes(o.status);
          const txId = (txIds[o.id] ?? "").trim();
          const reason = (reasons[o.id] ?? "").trim();
          return (
            <li key={o.id} className="rounded border border-border p-2 text-sm" data-testid={`order-exec-${o.id}`}>
              <div>
                <strong>{o.counterpart_name}</strong> {formatEur(String(o.amount))}
              </div>
              {o.status === "partially_executed" || paid > 0 ? (
                <p className="text-xs text-warning-fg" role="note">
                  {t("partial", { paid: formatEur((paid / 100).toFixed(2)), rest: formatEur((rest / 100).toFixed(2)) })}
                </p>
              ) : null}
              {open ? (
                <div className="mt-1 flex flex-col gap-1">
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("bankTransaction")}</span>
                    <input className={ui.input} value={txIds[o.id] ?? ""} onChange={(e) => setTxIds((m) => ({ ...m, [o.id]: e.target.value }))} />
                  </label>
                  <GatedAction
                    gate="G2"
                    url={`/api/bff/banking/payment-batches/${o2.batch_id}/bank-status`}
                    label={t("recordExecuted")}
                    lockedText={t("locked")}
                    hint={t("executedHint")}
                    blocked={txId.length === 0 || !o2.batch_id}
                    body={{ status: "executed", bank_transaction_id: txId, order_ids: [o.id] }}
                    onDone={() => router.refresh()}
                    testId={`order-exec-gate-${o.id}`}
                  />
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("reason")}</span>
                    <input className={ui.input} maxLength={2000} value={reasons[o.id] ?? ""} onChange={(e) => setReasons((m) => ({ ...m, [o.id]: e.target.value }))} />
                  </label>
                  <div>
                    <button type="button" className={ui.buttonSm} disabled={busy === o.id || reason.length < 3 || !o2.batch_id} onClick={() => void reject(o.id)}>
                      {t("recordRejected")}
                    </button>
                  </div>
                </div>
              ) : null}
              {errors[o.id] ? (
                <p role="alert" className={ui.alert}>
                  {errors[o.id]}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
