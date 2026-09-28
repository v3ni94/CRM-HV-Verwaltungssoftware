"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { BankAccountActions, isEnded } from "./BankAccountActions";
import { BankAccountApproval } from "./BankAccountApproval";
import { BankAccountForm } from "./BankAccountForm";

type BankAccount =
  components["schemas"]["mhvp__contacts__schemas__BankAccountOut"];

/** Reiter Bankverbindungen of the contact page: list (cards on phone width, table above),
 * four eyes release per account, and the CRM actions add, change as new version and end
 * (M5-01 addendum 28.09.2026). Editing needs contacts:update, releasing contacts:approve. */
export function BankAccountsSection({
  contactId,
  accounts,
  canEdit,
  canApprove,
  currentUserId,
  isPlatformAdmin = false,
}: {
  contactId: string;
  accounts: BankAccount[];
  canEdit: boolean;
  canApprove: boolean;
  currentUserId: string | null;
  isPlatformAdmin?: boolean;
}) {
  const t = useTranslations("Contacts");
  const tb = useTranslations("Contacts.bankAccounts");
  const tf = useTranslations("ContactForm");
  const [form, setForm] = useState<{ mode: "add" } | { mode: "replace"; account: BankAccount } | null>(null);
  const byId = new Map(accounts.map((a) => [a.id, a]));

  const meta = (b: BankAccount) => (
    <>
      {b.replaces_account_id && byId.has(b.replaces_account_id) ? (
        <span className="block text-xs text-muted">
          {tb("replaces", { iban: byId.get(b.replaces_account_id)?.iban_masked ?? "" })}
        </span>
      ) : null}
      {isEnded(b) && b.approval_status !== "rejected" ? (
        <span className="block text-xs text-muted">{tb("ended")}</span>
      ) : null}
    </>
  );

  const actions = (b: BankAccount) => (
    <div className="flex flex-col gap-1.5">
      <BankAccountApproval
        contactId={contactId}
        account={b}
        canApprove={canApprove}
        currentUserId={currentUserId}
        isPlatformAdmin={isPlatformAdmin}
      />
      <BankAccountActions
        contactId={contactId}
        account={b}
        canEdit={canEdit}
        canApprove={canApprove}
        currentUserId={currentUserId}
        isPlatformAdmin={isPlatformAdmin}
        onReplace={() => setForm({ mode: "replace", account: b })}
      />
    </div>
  );

  return (
    <div className="flex flex-col gap-3" data-testid="bank-accounts-section">
      <div className="flex flex-wrap items-start gap-2">
        <p className="text-xs text-muted">{t("bankApproval.hint")}</p>
        {canEdit && !form ? (
          <button
            type="button"
            className={`${ui.buttonSm} ml-auto`}
            onClick={() => setForm({ mode: "add" })}
          >
            {tb("add")}
          </button>
        ) : null}
      </div>
      {form ? (
        <BankAccountForm
          contactId={contactId}
          mode={form.mode}
          account={form.mode === "replace" ? form.account : undefined}
          onClose={() => setForm(null)}
        />
      ) : null}
      {accounts.length ? (
        <>
          {/* Phone width: one card per account so the release status and buttons stay visible
              without horizontal scrolling (review 26.09.2026, contacts B1). */}
          <ul className="flex flex-col gap-2 sm:hidden" data-testid="bank-accounts-cards">
            {accounts.map((b) => (
              <li key={b.id} className={`${ui.card} flex flex-col gap-1 text-sm`}>
                <span className="font-mono whitespace-nowrap">
                  {b.iban_masked}
                  {b.is_default ? (
                    <span className="ml-1 font-sans text-xs text-muted">{tf("defaultAccount")}</span>
                  ) : null}
                </span>
                {meta(b)}
                {b.kind ? <span className="text-xs text-muted">{tf(`accountKind.${b.kind}`)}</span> : null}
                <span className="text-xs text-muted">
                  {[b.bank_name, b.bic, b.holder].filter(Boolean).join(", ")}
                </span>
                <span className="text-xs text-muted">
                  {tf("validFrom")} {formatDate(b.valid_from)}
                  {b.valid_to ? `, ${tf("validTo")} ${formatDate(b.valid_to)}` : ""}
                </span>
                <div className="mt-1">{actions(b)}</div>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted">
                <tr>
                  <th className="py-1 pr-3 font-medium">{tf("iban")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("accountKindLabel")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("bic")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("bankName")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("holder")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("validFrom")}</th>
                  <th className="py-1 pr-3 font-medium">{tf("validTo")}</th>
                  <th className="py-1 font-medium">{t("bankApproval.title")}</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((b) => (
                  <tr key={b.id} className="border-b border-border align-top">
                    <td className="py-1.5 pr-3 font-mono whitespace-nowrap">
                      {b.iban_masked}
                      {b.is_default ? (
                        <span className="ml-1 font-sans text-xs text-muted">{tf("defaultAccount")}</span>
                      ) : null}
                      <span className="font-sans">{meta(b)}</span>
                    </td>
                    <td className="py-1.5 pr-3">{b.kind ? tf(`accountKind.${b.kind}`) : ""}</td>
                    <td className="py-1.5 pr-3">{b.bic ?? ""}</td>
                    <td className="py-1.5 pr-3">{b.bank_name ?? ""}</td>
                    <td className="py-1.5 pr-3">{b.holder ?? ""}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{formatDate(b.valid_from)}</td>
                    <td className="py-1.5 pr-3 whitespace-nowrap">{formatDate(b.valid_to)}</td>
                    <td className="py-1.5">{actions(b)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
    </div>
  );
}
