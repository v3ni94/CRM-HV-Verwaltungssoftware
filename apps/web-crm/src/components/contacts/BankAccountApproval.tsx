"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type BankAccount = components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const BADGE: Record<BankAccount["approval_status"], string> = {
  pending: ui.badgeWarning,
  approved: ui.badgeSuccess,
  rejected: ui.badgeDanger,
};

/** Four eyes release of a contact IBAN (M5-01): status badge and, for a second person with
 * contacts:approve, the release and reject buttons. The API enforces the same rule. */
export function BankAccountApproval({
  contactId,
  account,
  canApprove,
  currentUserId,
}: {
  contactId: string;
  account: BankAccount;
  canApprove: boolean;
  currentUserId: string | null;
}) {
  const t = useTranslations("Contacts");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const status = account.approval_status;
  const ownRequest = account.requested_by != null && account.requested_by === currentUserId;

  async function decide(action: "approve" | "reject") {
    if (action === "reject" && !window.confirm(t("bankApproval.rejectConfirm", { iban: account.iban_masked }))) return;
    setError(null);
    setBusy(true);
    const result = await bff(`/api/bff/contacts/${contactId}/bank-accounts/${account.id}/${action}`, {
      method: "POST",
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className={BADGE[status]}>{t(`bankApproval.${status}`)}</span>
      {status === "pending" && canApprove && !ownRequest ? (
        <>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void decide("approve")}>
            {t("bankApproval.approve")}
          </button>
          <button type="button" className={ui.button} disabled={busy} onClick={() => void decide("reject")}>
            {t("bankApproval.reject")}
          </button>
        </>
      ) : null}
      {status === "pending" && ownRequest ? (
        <span className="text-xs text-muted">{t("bankApproval.ownRequest")}</span>
      ) : null}
      {error ? (
        <span role="alert" className="text-xs text-danger-fg">
          {error}
        </span>
      ) : null}
    </div>
  );
}
