"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import { formatEur } from "@/components/portal/HoaAccountTable";
import type { OwnerAllocationUnit, OwnerRentalIncome, OwnerTakeoverProperty, OwnerTicket, PaymentResolution } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Eigentümerübersicht (M21-06, SA-05), lesend: beschlossene Zahlungen der Gemeinschaft mit
 *  Geltungsdauer und Zahlungsinformation sowie die für Eigentümer freigegebenen Meldungen zum
 *  Objekt. Reine Information: keine Zahlung wird ausgelöst, die individuelle Sollstellung
 *  steht im Hausgeldkonto. */
export function OwnerOverview({
  payments,
  note,
  tickets,
  allocations = [],
  income = [],
  takeover = [],
  takeoverNote = "",
}: {
  payments: PaymentResolution[];
  note: string;
  tickets: OwnerTicket[];
  allocations?: OwnerAllocationUnit[];
  income?: OwnerRentalIncome[];
  takeover?: OwnerTakeoverProperty[];
  takeoverNote?: string;
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
              {(p.own_share ?? []).map((share) => (
                <span key={share.unit_number} data-testid="owner-share">
                  {t("ownShare", { unit: share.unit_number })}:{" "}
                  {share.amount
                    ? `${formatEur(share.amount)}${share.instalments ? `, ${t("instalments", { count: share.instalments })}` : ""}`
                    : Object.entries(share.monthly ?? {})
                        .map(([component, value]) => `${component} ${formatEur(value)} ${t("perMonth")}`)
                        .join(", ")}
                </span>
              ))}
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
      {allocations.length > 0 ? (
        <section className="flex flex-col gap-3" aria-labelledby="owner-allocations">
          <h2 id="owner-allocations" className={ui.h2}>
            {t("allocationsTitle")}
          </h2>
          <ul className="flex flex-col gap-3">
            {allocations.map((unit) => (
              <li key={unit.unit_id} className={`${ui.card} flex flex-col gap-1 text-sm`}>
                <span className="font-medium">
                  {unit.property_name}, {t("unit")} {unit.unit_number}
                </span>
                {unit.keys.map((k) => (
                  <span key={k.code}>
                    {k.name}: {k.value ?? t("noValue")} {k.value ? k.unit_of_measure : ""}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {income.length > 0 ? (
        <section className="flex flex-col gap-3" aria-labelledby="owner-income">
          <h2 id="owner-income" className={ui.h2}>
            {t("incomeTitle")}
          </h2>
          <ul className="flex flex-col gap-3">
            {income.map((row) => (
              <li key={row.property_id} className={`${ui.card} flex flex-col gap-1 text-sm`}>
                <span className="font-medium">
                  {row.property_name}: {formatEur(row.total_gross)} {t("perMonth")}
                </span>
                {row.units.map((u) => (
                  <span key={u.unit_number}>
                    {t("unit")} {u.unit_number}: {formatEur(u.gross)}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {takeover.length > 0 ? (
        <section className="flex flex-col gap-3" aria-labelledby="owner-takeover" data-testid="owner-takeover">
          <h2 id="owner-takeover" className={ui.h2}>
            {t("takeoverTitle")}
          </h2>
          {takeoverNote ? <p className={ui.notice}>{takeoverNote}</p> : null}
          <ul className="flex flex-col gap-3">
            {takeover.map((prop) => (
              <li key={prop.property_id} className={`${ui.card} flex flex-col gap-1 text-sm`}>
                <span className="font-medium">
                  {prop.property_name}:{" "}
                  {prop.complete ? t("takeoverComplete") : t("takeoverOpen", { count: prop.open_count })}
                </span>
                <ul className="flex flex-col gap-1">
                  {prop.points.map((point) => (
                    <li key={point.category} className="flex flex-wrap items-center justify-between gap-2">
                      <span>{point.label}</span>
                      <span className={point.status === "open" || point.status === "requested" ? ui.badgeWarning : ui.badgeSuccess}>
                        {point.status_label}
                        {point.due_date && (point.status === "open" || point.status === "requested")
                          ? `, ${t("takeoverDue", { date: date(point.due_date) })}`
                          : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
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
