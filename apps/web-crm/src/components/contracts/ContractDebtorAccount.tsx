import Link from "next/link";
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DebtorAccountOut = { id: string; legal_entity_id: string; number: string; name: string };

export type TerminationReadingOut = { id: string; meter_id: string; meter_reading_id: string | null; value: string; read_at: string };

/** Debitorenkonto des Vertrags (6.9.2) mit Sprung in den Buchungskreis des Gläubigers
 *  (offene Posten unter /buchhaltung/[ledgerId]). Saldo und offene Posten liest die
 *  Buchhaltung; hier wird nichts gebucht. */
export function ContractDebtorAccount({
  account,
  ledgerId,
  ledgerName,
  moveInOn,
  moveOutOn,
  readings,
  meterLabels,
}: {
  account: DebtorAccountOut;
  ledgerId: string | null;
  ledgerName: string | null;
  moveInOn: string | null | undefined;
  moveOutOn: string | null | undefined;
  readings: TerminationReadingOut[];
  meterLabels: Record<string, string>;
}) {
  const t = useTranslations("contracts");
  return (
    <section className={ui.card} data-testid="contract-debtor-account">
      <h2 className={ui.h2}>{t("debtor.title")}</h2>
      <dl className="grid gap-2 text-sm sm:grid-cols-2">
        <dt className={ui.label}>{t("debtor.number")}</dt>
        <dd>{account.number}</dd>
        <dt className={ui.label}>{t("debtor.name")}</dt>
        <dd>{account.name}</dd>
        <dt className={ui.label}>{t("debtor.openItems")}</dt>
        <dd>
          {ledgerId ? (
            <Link href={`/buchhaltung/${ledgerId}`} className="hover:underline" data-testid="open-items-link">
              {ledgerName ?? t("debtor.openItemsLink")}
            </Link>
          ) : (
            t("debtor.noLedger")
          )}
        </dd>
        <dt className={ui.label}>{t("dates.moveInOn")}</dt>
        <dd>{moveInOn ? formatDate(moveInOn) : t("dates.none")}</dd>
        <dt className={ui.label}>{t("dates.moveOutOn")}</dt>
        <dd>{moveOutOn ? formatDate(moveOutOn) : t("dates.none")}</dd>
      </dl>
      {readings.length > 0 ? (
        <>
          <h3 className={`${ui.label} mt-3`}>{t("termination.meterReadings")}</h3>
          <ul className="text-sm">
            {readings.map((r) => (
              <li key={r.id}>
                {meterLabels[r.meter_id] ?? r.meter_id}: {r.value} ({formatDate(r.read_at)})
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
