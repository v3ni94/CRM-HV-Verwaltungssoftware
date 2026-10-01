"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { problemMessage, readProblem } from "@/lib/problem";
import { ui } from "@/lib/ui";

/** Q02 (M24-03, 7.8 W12): Gesamtabrechnung der WEG als PDF herunterladen. Der Server liefert das
 * PDF nur nach interner Freigabe und bei offenem Gate G4 (sonst Fehlermeldung statt Datei); alle
 * Werte stammen aus dem gespeicherten Stand, nichts wird neu berechnet. */
export function StatementPdfButton({ statementId, year, version }: { statementId: string; year: number; version: number }) {
  const t = useTranslations("HoaStatementPdf");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/bff/hoa/statements/${statementId}/pdf`, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) {
        setError(problemMessage(await readProblem(response), response.status));
        return;
      }
      const href = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = href;
      a.download = `gesamtabrechnung-${String(year)}-v${String(version)}.pdf`;
      a.click();
      URL.revokeObjectURL(href);
    } catch {
      setError(problemMessage(null, 0));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-1" data-testid="statement-pdf">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={ui.button} onClick={() => void download()} disabled={busy}>
          {t("download")}
        </button>
        <span className={ui.help}>{t("hint")}</span>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
