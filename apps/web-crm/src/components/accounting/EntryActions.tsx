"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type EntryActionRow = {
  id: string;
  status: string;
  kind: string;
  approved_by?: string | null;
  reversed_by_id?: string | null;
};

/** Journal row actions (M10-02): post a draft, second person check of an opening balance,
 *  delete a draft, reverse a posted entry with a reason. Posted content is never edited. */
export function EntryActions({
  ledgerId,
  entry,
  canCreate,
  canApprove,
}: {
  ledgerId: string;
  entry: EntryActionRow;
  canCreate: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("Bookkeeping");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reversing, setReversing] = useState(false);
  const [reason, setReason] = useState("");
  const base = `/api/bff/accounting/ledgers/${ledgerId}/entries/${entry.id}`;

  const run = async (path: string, init: RequestInit, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return;
    setBusy(true);
    setError(null);
    const res = await bff(path, init);
    setBusy(false);
    if (res.ok) {
      setReversing(false);
      setReason("");
      router.refresh();
    } else setError(res.message);
  };

  const draft = entry.status === "draft";
  const opening = entry.kind === "opening_balance";
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="flex flex-wrap gap-1">
        {draft && canApprove && opening && !entry.approved_by ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => run(`${base}/approve`, { method: "POST" }, t("actions.confirmApprove"))}>
            {t("actions.approve")}
          </button>
        ) : null}
        {draft && canCreate ? (
          <button
            type="button"
            className={ui.buttonSm}
            disabled={busy || (opening && !entry.approved_by)}
            title={opening && !entry.approved_by ? t("actions.needsApproval") : undefined}
            onClick={() => run(`${base}/post`, { method: "POST" }, t("actions.confirmPost"))}
          >
            {t("actions.post")}
          </button>
        ) : null}
        {draft && canCreate ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => run(base, { method: "DELETE" }, t("actions.confirmDelete"))}>
            {t("actions.delete")}
          </button>
        ) : null}
        {!draft && canCreate && !entry.reversed_by_id && entry.kind !== "reversal" ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setReversing((v) => !v)}>
            {t("actions.reverse")}
          </button>
        ) : null}
      </span>
      {reversing ? (
        <form
          aria-label={t("actions.reverse")}
          className="flex flex-col gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            void run(`${base}/reverse`, { method: "POST", body: JSON.stringify({ reason }) }, t("actions.confirmReverse"));
          }}
        >
          <label className={ui.label} htmlFor={`reason-${entry.id}`}>
            {t("actions.reason")}
          </label>
          <input id={`reason-${entry.id}`} required minLength={3} maxLength={2000} className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="submit" className={ui.danger} disabled={busy || reason.trim().length < 3}>
            {t("actions.reverseSubmit")}
          </button>
        </form>
      ) : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
