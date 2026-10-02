"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Out = { run_id: string; proposal_id: string | null };

/** Anhang als Rechnung vorschlagen (GAI-418): `POST /mail/messages/{id}/attachments/{id}/invoice-extraction`
 *  startet einen KI-Extraktionslauf (nur Vorschlag, Freigabe durch eine Person, Recht accounting:create).
 *  Nur PDF-Anhänge; die KI-Schalter und die Maskierung liegen in der API. */
export function MailInvoiceExtraction({ messageId, attachmentId, mimeType }: { messageId: string; attachmentId: string; mimeType?: string }) {
  const t = useTranslations("Aj17.invoice");
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (mimeType && mimeType !== "application/pdf") return null;
  const start = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Out>(`/api/bff/mail/messages/${messageId}/attachments/${attachmentId}/invoice-extraction`, { method: "POST", body: "{}" });
    setBusy(false);
    if (res.ok) setRun(res.data?.run_id ?? "");
    else setError(res.message);
  };
  return (
    <span className="inline-flex flex-col gap-1" data-testid="invoice-extraction">
      <button type="button" className={ui.buttonSm} disabled={busy || run !== null} onClick={() => void start()} title={t("help")}>
        {t("button")}
      </button>
      {run !== null ? <span role="status" className="text-xs text-muted">{t("started", { run })}</span> : null}
      {error ? <span role="alert" className={ui.alert}>{error}</span> : null}
    </span>
  );
}
