"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ScanOut = { events: number; noted: number };

/** Eigentümerwechsel auf offene Einsichtsanfragen prüfen (GAI-412): legt nur Prüfvermerke an,
 *  schließt nichts und widerruft kein Paket. Recht hoa:update. */
export function OwnershipScanButton({ canEdit }: { canEdit: boolean }) {
  const t = useTranslations("Aj17.ownerScan");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ScanOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!canEdit) return null;
  const run = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<ScanOut>("/api/bff/hoa/inspection-requests/ownership-transfers/scan", { method: "POST", body: "{}" });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };
  return (
    <section className={ui.card} data-testid="owner-scan">
      <p className={ui.help}>{t("help")}</p>
      <div className="mt-2">
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void run()}>
          {t("button")}
        </button>
      </div>
      {result ? (
        <p role="status" className="mt-2 text-sm" data-testid="owner-scan-result">
          {t("result", { events: result.events, noted: result.noted })}
        </p>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
