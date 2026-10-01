"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import type { AccountOption } from "./ReserveYears";

/** Bank account of the community (legal entity of the ledger) and ledger account of a reserve.
 *  The API checks both again (E01: the reserve belongs to the community, never to the manager). */
export function ReserveAccountFields({
  bankAccounts,
  accounts,
  bankAccountId,
  accountId,
  onBank,
  onAccount,
}: {
  bankAccounts: AccountOption[];
  accounts: AccountOption[];
  bankAccountId: string;
  accountId: string;
  onBank: (id: string) => void;
  onAccount: (id: string) => void;
}) {
  const t = useTranslations("HoaReserves");
  return (
    <>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("bankAccount")}</span>
        <select className={ui.input} value={bankAccountId} onChange={(e) => onBank(e.target.value)}>
          <option value="">{t("noneSelected")}</option>
          {bankAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("ledgerAccount")}</span>
        <select className={ui.input} value={accountId} onChange={(e) => onAccount(e.target.value)}>
          <option value="">{t("noneSelected")}</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}
