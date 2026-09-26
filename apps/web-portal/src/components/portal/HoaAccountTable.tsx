"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { HoaAccount, HoaAccountEntry } from "@/components/portal/types";
import { ui } from "@/lib/ui";

export function formatEur(value: string): string {
  return `${new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))} EUR`;
}

/** Running balance after every booking (charges add, payments and credit notes subtract),
 *  computed in cents to avoid float rounding; the last value equals the contract balance. */
export function runningBalances(entries: HoaAccountEntry[]): string[] {
  let cents = 0;
  return entries.map((entry) => {
    const amount = Math.round(Number(entry.amount) * 100);
    cents += entry.direction === "charge" ? amount : -amount;
    return (cents / 100).toFixed(2);
  });
}

/** Hausgeldkonto des Eigentümers (A51): nur gebuchte Einträge des Buchungskreises der
 *  Gemeinschaft, Sollstellungen und Zahlungen mit Saldo in 1.234,56 EUR. Keine Abrechnung,
 *  keine Rechtsfolge; der Hinweis kommt aus der API und wird immer angezeigt. Unterhalb von
 *  `md` wird je Buchung eine Karte gezeigt (Datum, Text, Betrag rechts, Saldo), ab `md` die
 *  Tabelle (O01); der Wechsel erfolgt über den CSS Breakpoint, beide Darstellungen liegen im
 *  Dokument. */
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
        <section key={contract.contract_number} className={`${ui.card} flex flex-col gap-3`} aria-labelledby={`hoa-${contract.contract_number}`}>
          <h2 id={`hoa-${contract.contract_number}`} className={ui.h2}>
            {t("contract")} {contract.contract_number}
          </h2>
          {contract.note ? <p className={ui.help}>{contract.note}</p> : null}
          {contract.entries.length > 0 ? (
            <>
            <ul className="flex flex-col gap-2 md:hidden" aria-label={`${t("tableCaption")} ${contract.contract_number}`} data-testid="hoa-cards">
              {(() => {
                const balances = runningBalances(contract.entries);
                return contract.entries.map((entry, i) => (
                  <li
                    key={i}
                    className={`rounded-md border border-border bg-surface px-3 py-2 ${entry.reversed ? "text-subtle" : ""}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-xs text-subtle">{date(entry.booking_date)}</span>
                        <span className={`text-sm ${entry.reversed ? "line-through" : ""}`}>
                          {entry.text}
                          {entry.reversed ? <span className="sr-only"> ({t("reversed")})</span> : null}
                        </span>
                        <span className="text-xs text-muted">{entry.direction === "charge" ? t("charge") : t("credit")}</span>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">
                        <span className={`whitespace-nowrap text-sm font-medium ${entry.reversed ? "line-through" : ""}`}>
                          {entry.direction === "credit" ? "-" : ""}
                          {formatEur(entry.amount)}
                        </span>
                        <span className="whitespace-nowrap text-xs text-muted">
                          {t("runningBalance")} {formatEur(balances[i] ?? "0")}
                        </span>
                      </div>
                    </div>
                  </li>
                ));
              })()}
            </ul>
            <div className={`${ui.tableScroll} hidden md:block`}>
              <table className={`${ui.table} ${ui.tableStickyCol}`}>
                <caption className="sr-only">
                  {t("tableCaption")} {contract.contract_number}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">{t("bookingDate")}</th>
                    <th scope="col">{t("text")}</th>
                    <th scope="col" className="num">
                      {t("charge")}
                    </th>
                    <th scope="col" className="num">
                      {t("credit")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {contract.entries.map((entry, i) => (
                    <tr key={i} className={entry.reversed ? "text-subtle line-through" : undefined}>
                      <td className="whitespace-nowrap">{date(entry.booking_date)}</td>
                      <td>
                        {entry.text}
                        {entry.reversed ? <span className="sr-only"> ({t("reversed")})</span> : null}
                      </td>
                      <td className="num whitespace-nowrap">{entry.direction === "charge" ? formatEur(entry.amount) : ""}</td>
                      <td className="num whitespace-nowrap">{entry.direction === "credit" ? formatEur(entry.amount) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          ) : contract.note ? null : (
            <p className={ui.help}>{t("noEntries")}</p>
          )}
          {contract.balance !== null ? (
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-sm sm:grid-cols-[12rem_1fr]">
              <dt className={ui.label}>{t("sumCharges")}</dt>
              <dd className="whitespace-nowrap text-right sm:text-left">{formatEur(contract.charges ?? "0")}</dd>
              <dt className={ui.label}>{t("sumCredits")}</dt>
              <dd className="whitespace-nowrap text-right sm:text-left">{formatEur(contract.credits ?? "0")}</dd>
              <dt className={ui.label}>{t("balance")}</dt>
              <dd className="text-right font-medium sm:text-left">
                <span className="whitespace-nowrap">{formatEur(contract.balance)}</span>{" "}
                <span className="text-xs font-normal text-subtle">
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
