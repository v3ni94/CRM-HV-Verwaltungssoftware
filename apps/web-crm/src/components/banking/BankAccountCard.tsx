"use client";

import { useTranslations } from "next-intl";

import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { accountLabel, type BankAccountOption } from "./bankAccountTypes";

/** Kontostand und letzte Umsätze eines ausgewählten Kontos (lesend). */
export function BankAccountCard({ account }: { account: BankAccountOption }) {
  const t = useTranslations("BankAccounts");
  return (
    <section className={ui.card} data-testid="bank-account-card">
      <h3 className={ui.h2}>{accountLabel(account)}</h3>
      <p className="mt-1 text-xs text-muted">
        {t(`kind.${account.kind}`)}, {t(`source.${account.source}`)}
        {account.legal_entity_name ? `, ${account.legal_entity_name}` : ""}
      </p>
      <p className="mt-2 text-sm">
        <span className={ui.subtitle}>{t("balance")}</span>{" "}
        <span className="text-lg font-semibold tabular-nums">
          {account.balance !== null ? formatEur(account.balance) : t("balanceUnknown")}
        </span>
        {account.balance_source ? <span className="ml-2 text-xs text-muted">{t(`balanceSource.${account.balance_source}`)}</span> : null}
        {account.balance_as_of ? <span className="ml-2 text-xs text-muted">{t("asOf", { date: formatDate(account.balance_as_of) })}</span> : null}
      </p>
      <h4 className={`${ui.subtitle} mt-3`}>{t("recent")}</h4>
      {account.recent_transactions.length === 0 ? (
        <p className="mt-1 text-sm text-muted">{t("noRecent")}</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1 text-sm">
          {account.recent_transactions.map((tx) => (
            <li key={tx.id} className="flex justify-between gap-2">
              <span className="truncate">
                <span className="tabular-nums text-muted">{formatDate(tx.booking_date)}</span> {tx.counterpart_name ?? ""}
                {tx.purpose ? <span className="text-muted"> {tx.purpose}</span> : null}
              </span>
              <span className="shrink-0 tabular-nums">{formatEur(tx.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
