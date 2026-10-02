"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { today as businessToday } from "@/lib/today";

type BankAccount =
  components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

const NOTE_MAX = 500;
const REASON_MAX = 500;


/** True when the account is closed for further changes: rejected IBAN or Gültig bis in the
 * past (the API answers 409 MHVP-CONT-0001 in that case). */
export function isEnded(account: BankAccount, day = businessToday()): boolean {
  return (
    account.approval_status === "rejected" ||
    (account.valid_to != null && account.valid_to < day)
  );
}

/** Change (new version) and end of an existing contact bank account plus the four eyes
 * decision on a pending end (M5-01 addendum 28.09.2026). Ending is applied at once only when
 * the caller holds contacts:approve and the contact is no legal entity; the API decides and
 * answers with ``pending_change`` otherwise. */
export function BankAccountActions({
  contactId,
  account,
  canEdit,
  canApprove,
  currentUserId,
  isPlatformAdmin = false,
  onReplace,
}: {
  contactId: string;
  account: BankAccount;
  canEdit: boolean;
  canApprove: boolean;
  currentUserId: string | null;
  isPlatformAdmin?: boolean;
  onReplace: () => void;
}) {
  const t = useTranslations("Contacts.bankAccounts");
  const router = useRouter();
  const id = useId();
  const [ending, setEnding] = useState(false);
  const [validTo, setValidTo] = useState(businessToday());
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [current, setCurrent] = useState<BankAccount>(account);

  const change = current.pending_change ?? null;
  const ownChange = change?.requested_by != null && change.requested_by === currentUserId;
  const mayDecide = change != null && canApprove && !ownChange && !isPlatformAdmin;
  const editable =
    canEdit && change == null && current.approval_status === "approved" && !isEnded(current);

  async function end(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (validTo < current.valid_from) {
      setError(t("validToBeforeFrom"));
      return;
    }
    setBusy(true);
    const result = await bff<BankAccount>(
      `/api/bff/contacts/${contactId}/bank-accounts/${account.id}/end`,
      {
        method: "POST",
        body: JSON.stringify({ valid_to: validTo, note: note.trim() || null }),
      },
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setCurrent(result.data);
    setEnding(false);
    setNotice(
      result.data.pending_change
        ? t("endPendingNotice", { date: formatDate(result.data.pending_change.valid_to) })
        : t("endedNotice", { iban: account.iban_masked, date: formatDate(result.data.valid_to) }),
    );
    router.refresh();
  }

  async function decide(action: "approve" | "reject") {
    if (!change) return;
    setError(null);
    setBusy(true);
    const body = action === "reject" && reason.trim() ? { reason: reason.trim() } : {};
    const result = await bff<BankAccount>(
      `/api/bff/contacts/${contactId}/bank-accounts/${account.id}/changes/${change.id}/${action}`,
      { method: "POST", body: JSON.stringify(body) },
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setCurrent(result.data);
    setRejecting(false);
    setNotice(t(action === "approve" ? "changeApproved" : "changeRejected"));
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-1.5" data-testid="bank-account-actions">
      {change ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className={ui.badgeWarning}>
            {t("pendingEnd", { date: formatDate(change.valid_to) })}
          </span>
          {mayDecide && !rejecting ? (
            <>
              <button
                type="button"
                className={ui.buttonSm}
                disabled={busy}
                onClick={() => void decide("approve")}
              >
                {t("confirm")}
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
      ) : null}
      {change?.note ? (
        <p className="text-xs text-muted">{t("pendingEndNote", { note: change.note })}</p>
      ) : null}
      {change && ownChange ? <p className="text-xs text-muted">{t("pendingOwn")}</p> : null}
      {change && !ownChange && !isPlatformAdmin && !canApprove ? (
        <p className="text-xs text-muted">{t("pendingNoPermission")}</p>
      ) : null}
      {rejecting && change ? (
        <form
          className="flex max-w-md flex-col gap-2"
          aria-label={t("rejectTitle", { iban: account.iban_masked })}
          onSubmit={(event) => {
            event.preventDefault();
            void decide("reject");
          }}
        >
          <label htmlFor={`${id}-reason`} className={ui.label}>
            {t("rejectReason")}
          </label>
          <textarea
            id={`${id}-reason`}
            className={ui.input}
            rows={2}
            required
            maxLength={REASON_MAX}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.danger} disabled={busy || !reason.trim()}>
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
      {editable && !ending ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.buttonSm} onClick={onReplace}>
            {t("replace")}
          </button>
          <button type="button" className={ui.buttonSm} onClick={() => setEnding(true)}>
            {t("end")}
          </button>
        </div>
      ) : null}
      {ending ? (
        <form
          className="flex max-w-md flex-col gap-2"
          aria-label={t("endTitle", { iban: account.iban_masked })}
          onSubmit={(event) => void end(event)}
        >
          <label htmlFor={`${id}-valid-to`} className={ui.label}>
            {t("endValidTo")}
          </label>
          <input
            id={`${id}-valid-to`}
            type="date"
            className={ui.input}
            required
            value={validTo}
            onChange={(event) => setValidTo(event.target.value)}
          />
          <label htmlFor={`${id}-note`} className={ui.label}>
            {t("endNote")}
          </label>
          <textarea
            id={`${id}-note`}
            className={ui.input}
            rows={2}
            maxLength={NOTE_MAX}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            aria-describedby={`${id}-note-help`}
          />
          <span id={`${id}-note-help`} className={ui.help}>
            {t("endNoteHelp", { max: NOTE_MAX })}
          </span>
          <p className={ui.help}>{t("fourEyesHint")}</p>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.danger} disabled={busy}>
              {t("endSubmit")}
            </button>
            <button
              type="button"
              className={ui.button}
              disabled={busy}
              onClick={() => setEnding(false)}
            >
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
      {notice ? (
        <p role="status" className="text-xs text-success-fg">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-danger-fg">
          {error}
        </p>
      ) : null}
    </div>
  );
}
