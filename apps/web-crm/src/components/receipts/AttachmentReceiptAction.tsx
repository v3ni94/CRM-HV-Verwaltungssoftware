"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type AttachmentReceiptDraft = { id: string; status: string };

/** "Als Rechnung erfassen" on one mail attachment (M14): starts the receipt extraction via
 *  `POST /receipts/drafts` with `source=mail_attachment` and links to the draft in the
 *  Belegeingang. The draft is a proposal for review; the invoice is created only after a
 *  person confirms the values there (rule 0.1.6), never here. Used in the mail view and in
 *  the ticket view. */
export function AttachmentReceiptAction({
  messageId,
  documentId,
  label,
  onCreated,
}: {
  messageId: string;
  documentId: string;
  label?: string;
  onCreated?: (draft: AttachmentReceiptDraft) => void;
}) {
  const t = useTranslations("Receipts.attachment");
  const [busy, setBusy] = useState(false);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<AttachmentReceiptDraft>("/api/bff/receipts/drafts", {
      method: "POST",
      body: JSON.stringify({ document_id: documentId, source: "mail_attachment", message_id: messageId }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(t("failed", { reason: res.message }));
      return;
    }
    setDraftId(res.data.id);
    onCreated?.(res.data);
  };

  if (draftId) {
    return (
      <Link href={`/rechnungen/belegeingang?entwurf=${draftId}`} className="text-xs font-medium text-accent hover:underline">
        {t("openDraft")}
      </Link>
    );
  }

  return (
    <span className="flex flex-col gap-1">
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void start()}>
        {label ? `${label}: ` : ""}
        {t("capture")}
      </button>
      {error ? (
        <span role="alert" className="text-xs text-danger-fg">
          {error}
        </span>
      ) : null}
    </span>
  );
}
