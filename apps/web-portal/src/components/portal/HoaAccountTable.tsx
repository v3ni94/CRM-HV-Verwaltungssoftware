"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { HoaAccount } from "@/components/portal/types";
import { ui } from "@/lib/ui";

export function formatEur(value: string): string {
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))} EUR`;
}

/** Hausgeldkonto des Eigentümers (A51): nur gebuchte Einträge des Buchungskreises der
 *  Gemeinschaft, Sollstellungen und Zahlungen mit Saldo in 1.234,56 EUR. Keine Abrechnung,
 *  keine Rechtsfolge; der Hinweis kommt aus der API und wird immer angezeigt. */
export function HoaAccountTable({ account }: { account: HoaAccount }) {
  const t = useTranslations("HoaAccount");
  const format = useFormatter();
  const date = (value: string) =>
    format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" });
  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{account.note}</p>
      {account.legacy_note ? <p className={ui.notice}>{account.legacy_note}</p> : null}
      {account.contracts.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      {account.contracts.map((contract) => (
        <section key={contract.contract_number} className={`${ui.card} flex flex-col gap-3`}>
          <h2 className={ui.h2}>
            {t("contract")} {contract.contract_number}
          </h2>
          {contract.note ? <p className={ui.help}>{contract.note}</p> : null}
          {contract.entries.length > 0 ? (
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("bookingDate")}</th>
                  <th>{t("text")}</th>
                  <th>{t("charge")}</th>
                  <th>{t("credit")}</th>
                </tr>
              </thead>
              <tbody>
                {contract.entries.map((entry, i) => (
                  <tr key={i} className={entry.reversed ? "text-subtle line-through" : undefined}>
                    <td>{date(entry.booking_date)}</td>
                    <td>{entry.text}</td>
                    <td>{entry.direction === "charge" ? formatEur(entry.amount) : ""}</td>
                    <td>{entry.direction === "credit" ? formatEur(entry.amount) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : contract.note ? null : (
            <p className={ui.help}>{t("noEntries")}</p>
          )}
          {contract.balance !== null ? (
            <dl className="grid grid-cols-2 gap-1 text-sm sm:grid-cols-[12rem_1fr]">
              <dt className={ui.label}>{t("sumCharges")}</dt>
              <dd>{formatEur(contract.charges ?? "0")}</dd>
              <dt className={ui.label}>{t("sumCredits")}</dt>
              <dd>{formatEur(contract.credits ?? "0")}</dd>
              <dt className={ui.label}>{t("balance")}</dt>
              <dd className="font-medium">
                {formatEur(contract.balance)}{" "}
                <span className="text-xs text-subtle">
                  {Number(contract.balance) > 0 ? t("balanceOwed") : Number(contract.balance) < 0 ? t("balanceCredit") : t("balanceEven")}
                </span>
              </dd>
            </dl>
          ) : null}
        </section>
      ))}
    </div>
  );
}
