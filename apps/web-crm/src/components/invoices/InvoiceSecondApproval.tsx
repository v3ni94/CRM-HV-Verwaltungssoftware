"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type ApprovalState = {
  enabled: boolean;
  limit_amount: string | null;
  second_approval_required: boolean;
  second_approval_valid: boolean;
  second_approved_by: string | null;
};

/** GAF-06: second approval above the amount limit (four eyes, 7). The API refuses the person
 *  who recorded or first approved the invoice; the button only offers the action. */
export function InvoiceSecondApproval({ invoiceId, canApprove }: { invoiceId: string; canApprove: boolean }) {
  const t = useTranslations("LedgerExtras.approval");
  const router = useRouter();
  const [state, setState] = useState<ApprovalState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const base = `/api/bff/accounting/tax/invoices/${invoiceId}`;

  const load = useCallback(async () => {
    const res = await bff<ApprovalState>(`${base}/approval`);
    if (res.ok) setState(res.data);
    else setError(res.message);
  }, [base]);
  useEffect(() => {
    void load();
  }, [load]);

  const approve = async () => {
    if (!window.confirm(t("confirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<ApprovalState>(`${base}/second-approval`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setState(res.data);
    setDone(true);
    router.refresh();
  };

  if (!state && !error) return null;
  if (state && !state.enabled && !state.second_approval_required) return null;
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("title")} data-testid="second-approval">
      <h2 className={ui.h2}>{t("title")}</h2>
      {state ? (
        <p className="text-sm">
          {state.second_approval_valid
            ? t("valid")
            : state.second_approval_required
              ? t("required", { limit: state.limit_amount ? formatEur(state.limit_amount) : "" })
              : t("off")}
        </p>
      ) : null}
      {state && state.second_approval_required && !state.second_approval_valid && canApprove ? (
        <div className={ui.formActions}>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void approve()}>
            {t("action")}
          </button>
        </div>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {t("done")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
