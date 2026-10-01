"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Reference to the approval workflow of an order (GA04-07). There is no workflow table yet
 *  (AA05-01), so the reference is entered as an id; the board vote stays the effective approval. */
export function WorkOrderWorkflowRef({ orderId, initial, canEdit }: { orderId: string; initial: string | null; canEdit: boolean }) {
  const t = useTranslations("WorkOrders");
  const [value, setValue] = useState(initial ?? "");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed && !UUID.test(trimmed)) {
      setMessage({ ok: false, text: t("workflowInvalid") });
      return;
    }
    const res = await bff(`/api/bff/work-orders/${orderId}/approval-workflow`, {
      method: "PATCH",
      body: JSON.stringify({ approval_workflow_id: trimmed || null }),
    });
    setMessage(res.ok ? { ok: true, text: t("workflowSaved") } : { ok: false, text: res.message });
  }

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-2`} aria-label={t("workflowTitle")}>
      <h2 className="text-base font-semibold">{t("workflowTitle")}</h2>
      <label className={ui.label}>
        {t("workflowId")}
        <input className={ui.input} value={value} disabled={!canEdit} onChange={(e) => setValue(e.target.value)} />
      </label>
      <p className={ui.help}>{t("workflowHint")}</p>
      {message ? (
        <p role="status" className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
      {canEdit ? (
        <div>
          <button type="submit" className={ui.primary}>
            {t("workflowSave")}
          </button>
        </div>
      ) : null}
    </form>
  );
}
