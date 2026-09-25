"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** One-click forwarding of a company invoice to the invoicing mailbox (M32); the sender is
 *  remembered on the approved list so future mails are recognized. */
export function ForwardInvoiceButton({
  messageId,
  suggested,
}: {
  messageId: string;
  suggested: boolean;
}) {
  const t = useTranslations("MailForwarding");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forward = async () => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/mail/messages/${messageId}/forward-invoice`, {
      method: "POST",
      body: JSON.stringify({ remember_sender: true }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.refresh();
  };

  return (
    <span className="inline-flex flex-col gap-1">
      <span className="inline-flex items-center gap-1.5">
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={forward}>
          {t("forward")}
        </button>
        {suggested ? <span className={ui.badgeGold}>{t("suggested")}</span> : null}
      </span>
      {error ? <span className="text-xs text-danger-fg">{error}</span> : null}
    </span>
  );
}
