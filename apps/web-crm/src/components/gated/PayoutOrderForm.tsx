"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { GateStatusNotice } from "./GateStatusNotice";
import { useReleaseGate } from "./useReleaseGate";

export const PAYOUT_REASONS = ["owner_payout", "statement_credit", "deposit_refund", "other_refund"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type OrderOut = { id: string; amount: string; status: string; counterpart_name: string };

/**
 * GAI-402 (AJ28): payout without invoice as a draft order. Only with a reason (Begründung) from
 * the API list; held behind G2 (payment initiation) until the management releases it (AJ28-02).
 * The draft itself still needs the four eyes order approval of the payment run.
 */
export function PayoutOrderForm() {
  const t = useTranslations("gatedMasks.payout");
  const state = useReleaseGate("G2");
  const [form, setForm] = useState({ open_item_id: "", contact_bank_account_id: "", property_bank_account_id: "", execution_date: "", reason: "", purpose: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<OrderOut | null>(null);

  const idsValid = UUID.test(form.open_item_id) && UUID.test(form.contact_bank_account_id) && UUID.test(form.property_bank_account_id);
  const complete = idsValid && Boolean(form.execution_date) && Boolean(form.reason);
  const open = state.status === "open";

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!open || !complete || busy) return;
    setBusy(true);
    setError(null);
    const body = { ...form, purpose: form.purpose.trim() || undefined };
    const res = await bff<OrderOut>("/api/bff/accounting/payment-runs/payout-orders", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) setError(res.message);
    else setCreated(res.data);
  };

  const field = (key: "open_item_id" | "contact_bank_account_id" | "property_bank_account_id") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${key}`)}</span>
      <input className={ui.input} value={form[key]} onChange={set(key)} />
    </label>
  );

  return (
    <form className={`${ui.card} flex flex-col gap-2`} onSubmit={(e) => void submit(e)} data-testid="payout-order-form">
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <p className={ui.help}>{t("intro")}</p>
      {field("open_item_id")}
      {field("contact_bank_account_id")}
      {field("property_bank_account_id")}
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("fields.execution_date")}</span>
        <input type="date" className={ui.input} value={form.execution_date} onChange={set("execution_date")} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("fields.reason")}</span>
        <select className={ui.input} value={form.reason} onChange={set("reason")} required>
          <option value="">{t("reasonPlaceholder")}</option>
          {PAYOUT_REASONS.map((r) => (
            <option key={r} value={r}>
              {t(`reasons.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("fields.purpose")}</span>
        <input className={ui.input} value={form.purpose} maxLength={140} onChange={set("purpose")} />
      </label>
      {!form.reason ? <p className={ui.help}>{t("reasonRequired")}</p> : null}
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={!open || !complete || busy} aria-busy={busy}>
          {t("submit")}
        </button>
      </div>
      <GateStatusNotice gate="G2" state={state} lockedText={t("locked")} />
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {created ? (
        <p role="status" className={ui.success}>
          {t("created", { amount: formatEur(created.amount), name: created.counterpart_name })}
        </p>
      ) : null}
    </form>
  );
}
