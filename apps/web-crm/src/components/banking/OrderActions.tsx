"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Four eyes approval (M15): the API refuses a second approval by the same person; any change
 *  voids approvals. Creating the payment file needs G2 and is not offered here. */
export function OrderActions({ id, status }: { id: string; status: string }) {
  const t = useTranslations("Payments");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (action: "approve" | "cancel") => {
    if (action === "cancel" && !window.confirm(t("confirmCancel"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/banking/payment-orders/${id}/${action}`, { method: "POST" });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  if (status !== "draft" && status !== "approved") return null;
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="flex gap-2">
        {status === "draft" ? (
          <button type="button" className={ui.button} onClick={() => act("approve")} disabled={busy}>
            {t("approve")}
          </button>
        ) : null}
        <button type="button" className={ui.button} onClick={() => act("cancel")} disabled={busy}>
          {t("cancel")}
        </button>
      </span>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
