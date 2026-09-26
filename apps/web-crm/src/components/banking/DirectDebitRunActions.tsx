"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Lastschriftlauf (M15, pain.008): Freigabe durch zwei verschiedene Personen, Verwerfen und
 *  Datei als Dokument ablegen. Die Ausgabe der Datei (Download) bleibt hinter G2 und wird hier
 *  nicht angeboten; der Hinweis steht sichtbar am Lauf statt eines toten Buttons. */
export function DirectDebitRunActions({ id, status, approvals }: { id: string; status: string; approvals: number }) {
  const t = useTranslations("DirectDebits");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (action: "approve" | "cancel" | "file") => {
    if (action === "cancel" && !window.confirm(t("confirmCancel"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/direct-debits/${id}/${action}`, { method: "POST" });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const canApprove = status === "draft";
  const canFile = status === "approved" && approvals >= 2;
  const canCancel = status === "draft" || status === "approved" || status === "file_generated";
  if (!canApprove && !canFile && !canCancel) return null;
  return (
    <span className="inline-flex flex-col gap-1">
      <span className="flex flex-wrap gap-2">
        {canApprove ? (
          <button type="button" className={ui.button} onClick={() => act("approve")} disabled={busy}>
            {t("approve")}
          </button>
        ) : null}
        {canFile ? (
          <button type="button" className={ui.button} onClick={() => act("file")} disabled={busy}>
            {t("generateFile")}
          </button>
        ) : null}
        {canCancel ? (
          <button type="button" className={ui.button} onClick={() => act("cancel")} disabled={busy}>
            {t("cancel")}
          </button>
        ) : null}
      </span>
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
