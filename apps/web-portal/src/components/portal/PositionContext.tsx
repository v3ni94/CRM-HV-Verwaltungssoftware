"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { formatEur } from "@/components/portal/HoaAccountTable";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Context = {
  booking: { booking_date: string; text: string; reference: string | null; lines: { account_number: string; account_name: string; debit: string; credit: string }[] } | null;
  invoice: { number: string; invoice_date: string; service_from: string | null; service_to: string | null; gross: string; vendor_name: string | null } | null;
  order: { status: string; description: string } | null;
  contract: { title?: string } | null;
  payment: { status: string; execution_date: string; amount: string } | null;
  allocation: { key_code: string | null; key_name: string | null; basis: string; amount: string } | null;
  previous_year: { account: string | null; current: string; previous: string; difference: string } | null;
  missing: string[];
  note: string;
};

/** Kontext einer Prüfposition (PÜ07, M25-04): Buchung, Rechnung, Auftrag, Zahlung, Umlageschlüssel
 *  und Vorjahr nebeneinander, nur lesend und auf Abruf. */
export function PositionContext({ engagementId, itemId }: { engagementId: string; itemId: string }) {
  const t = useTranslations("Audit.context");
  const [data, setData] = useState<Context | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError(null);
    const result = await bff<Context>(`/api/bff/portal/board/engagements/${engagementId}/positions/${itemId}/context`);
    if (result.ok) setData(result.data);
    else setError(result.message);
    setBusy(false);
  }

  if (!data) {
    return (
      <div className="flex flex-col gap-1">
        <button type="button" className={ui.buttonSm} onClick={load} disabled={busy}>
          {t("show")}
        </button>
        {error ? <span role="alert" className="text-sm text-danger">{error}</span> : null}
      </div>
    );
  }
  const row = (label: string, value: string | null | undefined) =>
    value ? (
      <div className="flex flex-wrap gap-x-2">
        <dt className="text-subtle">{label}</dt>
        <dd>{value}</dd>
      </div>
    ) : null;
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm" data-testid="position-context">
      <dl className="flex flex-col gap-1">
        {data.booking ? row(t("booking"), `${data.booking.text}${data.booking.lines.length ? `: ${data.booking.lines.map((l) => `${l.account_number} ${Number(l.debit) > 0 ? "S" : "H"} ${formatEur(Number(l.debit) > 0 ? l.debit : l.credit)}`).join(", ")}` : ""}`) : null}
        {data.invoice ? row(t("invoice"), `${data.invoice.number}, ${data.invoice.vendor_name ?? ""}, ${formatEur(data.invoice.gross)}${data.invoice.service_from ? `, ${t("service")} ${data.invoice.service_from} ${data.invoice.service_to ?? ""}` : ""}`) : null}
        {data.order ? row(t("order"), `${data.order.description} (${data.order.status})`) : null}
        {data.contract ? row(t("contract"), data.contract.title) : null}
        {data.payment ? row(t("payment"), `${data.payment.status}, ${data.payment.execution_date}, ${formatEur(data.payment.amount)}`) : null}
        {data.allocation ? row(t("allocation"), `${data.allocation.key_name ?? data.allocation.key_code ?? ""}, ${data.allocation.basis}`) : null}
        {data.previous_year
          ? row(t("previousYear"), `${data.previous_year.account ?? ""}: ${formatEur(data.previous_year.current)} / ${formatEur(data.previous_year.previous)} (${formatEur(data.previous_year.difference)})`)
          : null}
      </dl>
      {data.missing.length > 0 ? (
        <ul className="text-danger" data-testid="position-missing">
          {data.missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      ) : null}
      <p className="text-xs text-subtle">{data.note}</p>
    </div>
  );
}
