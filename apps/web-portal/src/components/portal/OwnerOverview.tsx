"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { formatEur } from "@/components/portal/HoaAccountTable";
import type { OwnerTicket, PaymentResolution } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Eigentümerübersicht (M21-06, SA-05), lesend: beschlossene Zahlungen der Gemeinschaft mit
 *  Geltungsdauer und Zahlungsinformation sowie die für Eigentümer freigegebenen Meldungen zum
 *  Objekt. Reine Information: keine Zahlung wird ausgelöst, die individuelle Sollstellung
 *  steht im Hausgeldkonto. */
export function OwnerOverview({
  payments,
  note,
  tickets,
}: {
  payments: PaymentResolution[];
  note: string;
  tickets: OwnerTicket[];
}) {
  const t = useTranslations("OwnerOverview");
  const format = useFormatter();
  const date = (value: string | null) =>
    value ? format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" }) : t("open");
  return (
    <div className={ui.sectionGap}>
      <section className="flex flex-col gap-3" aria-labelledby="owner-payments">
        <h2 id="owner-payments" className={ui.h2}>
          {t("paymentsTitle")}
        </h2>
        <p className={ui.notice}>{note}</p>
        {payments.length === 0 ? <p className="text-sm text-muted">{t("paymentsEmpty")}</p> : null}
        <ul className="flex flex-col gap-3">
          {payments.map((p) => (
            <li key={p.resolution_id} className={`${ui.card} flex flex-col gap-1 text-sm`}>
              <span className="font-medium">
                {t("resolution", { number: p.number })}: {p.subject}
              </span>
              <span className="text-subtle">
                {t(`kind.${p.kind}`)}, {t("decidedOn")} {date(p.decided_on)}
              </span>
              <span>
                {t("validity")}: {date(p.valid_from)} {t("until")} {date(p.valid_to)}
              </span>
              {p.rhythm ? (
                <span>
                  {t("rhythm")}: {p.rhythm}
                  {p.due_day ? `, ${t("dueDay", { day: p.due_day })}` : ""}
                </span>
              ) : null}
              {p.total ? (
                <span>
                  {t("total")}: {formatEur(p.total)}
                  {p.instalments ? `, ${t("instalments", { count: p.instalments })}` : ""}
                </span>
              ) : null}
              {p.purpose ? <span>{p.purpose}</span> : null}
              {p.sepa ? (
                <span className="break-all" data-testid="owner-sepa">
                  {t("payee")}: {p.sepa.holder}, {p.sepa.iban}
                  {p.sepa.bic ? `, ${p.sepa.bic}` : ""}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="flex flex-col gap-3" aria-labelledby="owner-tickets">
        <h2 id="owner-tickets" className={ui.h2}>
          {t("ticketsTitle")}
        </h2>
        {tickets.length === 0 ? <p className="text-sm text-muted">{t("ticketsEmpty")}</p> : null}
        <ul className="flex flex-col gap-2">
          {tickets.map((row) => (
            <li key={row.id} className={ui.card}>
              <span className="font-medium">
                {row.number}: {row.title}
              </span>{" "}
              <span className={ui.badge}>{row.status}</span>
            </li>
          ))}
        </ul>
        <Link href="/hausgeldkonto" className="text-sm underline">
          {t("toAccount")}
        </Link>
      </section>
    </div>
  );
}
