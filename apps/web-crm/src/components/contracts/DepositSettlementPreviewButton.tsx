"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

/** GAG-29: PDF-Vorschau einer gespeicherten Kautionsabrechnung (Entwurf). Der Server rendert das
 * Schreiben aus dem gespeicherten Stand; es wird nichts abgelegt, nichts versendet und nichts
 * gebucht. Das PDF öffnet in einem neuen Tab (Muster StatementPdfButton). */
export function DepositSettlementPreviewButton({ contractId, settlementId }: { contractId: string; settlementId: string }) {
  const t = useTranslations("Deposits");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/bff/contracts/${contractId}/deposit-settlements/${settlementId}/document-preview`, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) {
        setError(problemMessage(await readProblem(response), response.status));
        return;
      }
      const href = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = href;
      a.target = "_blank";
      a.rel = "noopener";
      a.click();
      setTimeout(() => URL.revokeObjectURL(href), 60_000);
    } catch {
      setError(problemMessage(null, 0));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-1" data-testid="deposit-settlement-preview">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.buttonSm} onClick={() => void open()} disabled={busy}>
          {t("settlement.previewDocument")}
        </button>
        <span className={ui.help}>{t("settlement.previewDocumentHint")}</span>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
