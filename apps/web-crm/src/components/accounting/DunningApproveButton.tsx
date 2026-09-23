"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Approval by a second person (M16); the API also refuses it for a non leading ledger. */
export function DunningApproveButton({ runId }: { runId: string }) {
  const t = useTranslations("Dunning");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const approve = async () => {
    if (!window.confirm(t("confirmApprove"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/dunning-runs/${runId}/approve`, { method: "POST" });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <button type="button" className={ui.primary} onClick={approve} disabled={busy}>
        {t("approve")}
      </button>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
