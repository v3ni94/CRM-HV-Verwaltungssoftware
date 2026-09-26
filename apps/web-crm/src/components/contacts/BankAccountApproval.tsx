"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type BankAccount =
  components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const BADGE: Record<BankAccount["approval_status"], string> = {
  pending: ui.badgeWarning,
  approved: ui.badgeSuccess,
  rejected: ui.badgeDanger,
};

const REASON_MAX = 500;

/** Four eyes release of a contact IBAN (M5-01): status badge with decision date and, for a
 * second person with contacts:approve, the release button and a reject form with a reason.
 * The requester and platform admins never decide; the API enforces the same rule
 * (review 26.09.2026, contacts B3/B4). */
export function BankAccountApproval({
  contactId,
  account,
  canApprove,
  currentUserId,
  isPlatformAdmin = false,
}: {
  contactId: string;
  account: BankAccount;
  canApprove: boolean;
  currentUserId: string | null;
  isPlatformAdmin?: boolean;
}) {
  const t = useTranslations("Contacts.bankApproval");
  const router = useRouter();
  const reasonId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [decided, setDecided] = useState<BankAccount | null>(null);
  const current = decided ?? account;
  const status = current.approval_status;
  const ownRequest =
    account.requested_by != null && account.requested_by === currentUserId;
  const mayDecide =
    status === "pending" && canApprove && !ownRequest && !isPlatformAdmin;

  async function decide(action: "approve" | "reject") {
    setError(null);
    setBusy(true);
    const body =
      action === "reject" && reason.trim() ? { reason: reason.trim() } : {};
    const result = await bff<BankAccount>(
      `/api/bff/contacts/${contactId}/bank-accounts/${account.id}/${action}`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDecided(result.data);
    setRejecting(false);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-1.5" data-testid="bank-approval">
      <div className="flex flex-wrap items-center gap-2">
        <span className={BADGE[status]}>{t(status)}</span>
        {status !== "pending" && current.decided_at ? (
          <span className="text-xs text-muted">
            {t("decidedAt", { date: formatDateTime(current.decided_at) })}
          </span>
        ) : null}
        {mayDecide && !rejecting ? (
          <>
            <button
              type="button"
              className={ui.buttonSm}
              disabled={busy}
              onClick={() => void decide("approve")}
            >
              {t("approve")}
            </button>
            <button
              type="button"
              className={ui.buttonSm}
              disabled={busy}
              onClick={() => setRejecting(true)}
            >
              {t("reject")}
            </button>
          </>
        ) : null}
      </div>
      {status === "pending" && ownRequest ? (
        <p className="text-xs text-muted">{t("ownRequest")}</p>
      ) : null}
      {status === "pending" && !ownRequest && isPlatformAdmin ? (
        <p className="text-xs text-muted">{t("platformAdmin")}</p>
      ) : null}
      {status === "pending" &&
      !ownRequest &&
      !isPlatformAdmin &&
      !canApprove ? (
        <p className="text-xs text-muted">{t("noPermission")}</p>
      ) : null}
      {decided ? (
        <p role="status" className="text-xs text-success-fg">
          {t(
            decided.approval_status === "approved"
              ? "approvedNotice"
              : "rejectedNotice",
            { iban: account.iban_masked },
          )}
        </p>
      ) : null}
      {rejecting ? (
        <form
          className="flex max-w-md flex-col gap-2"
          aria-label={t("rejectTitle", { iban: account.iban_masked })}
          onSubmit={(event) => {
            event.preventDefault();
            void decide("reject");
          }}
        >
          <label htmlFor={reasonId} className={ui.label}>
            {t("rejectReason")}
          </label>
          <textarea
            id={reasonId}
            className={ui.input}
            rows={2}
            required
            maxLength={REASON_MAX}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-describedby={`${reasonId}-help`}
          />
          <span id={`${reasonId}-help`} className={ui.help}>
            {t("rejectReasonHelp", { max: REASON_MAX })}
          </span>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              className={ui.danger}
              disabled={busy || !reason.trim()}
            >
              {t("rejectSubmit")}
            </button>
            <button
              type="button"
              className={ui.button}
              disabled={busy}
              onClick={() => setRejecting(false)}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-danger-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
