"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

/**
 * GAL-304: preview "Skonto ziehen" at a chosen payment date. Shows the discount and the
 * payable amount from `GET /accounting/invoices/{id}/discount`; nothing is posted or paid here,
 * the discount is applied by the payment run.
 */
export function InvoiceDiscountPreview({
  invoiceId,
  discountPercent,
  discountUntil,
  today,
}: {
  invoiceId: string;
  discountPercent: string | null;
  discountUntil: string | null;
  today: string;
}) {
  const t = useTranslations("Invoices");
  const [payDate, setPayDate] = useState(today);
  const [result, setResult] = useState<{ discount: string; payable: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!discountPercent || !discountUntil) return null;
  const expired = payDate > discountUntil;
  const run = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ discount: string; payable: string }>(`/api/bff/accounting/invoices/${invoiceId}/discount?pay_date=${encodeURIComponent(payDate)}`);
    setBusy(false);
    if (res.ok) setResult(res.data);
    else {
      setResult(null);
      setError(res.message);
    }
  };
  return (
    <section className="flex flex-col gap-2" data-testid="discount-preview">
      <h2 className={ui.h2}>{t("discount.title")}</h2>
      <p className={ui.help}>{t("discount.hint", { percent: discountPercent, until: formatDate(discountUntil) })}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("discount.payDate")}</span>
          <input className={ui.input} type="date" value={payDate} onChange={(e) => { setPayDate(e.target.value); setResult(null); }} />
        </label>
        <button type="button" className={ui.button} disabled={busy || !payDate} onClick={run}>{t("discount.preview")}</button>
      </div>
      {expired ? <p className={ui.help} data-testid="discount-expired">{t("discount.expired")}</p> : null}
      {result ? (
        <p className="text-sm" data-testid="discount-result">
          {Number(result.discount) === 0 ? t("discount.none", { payable: formatEur(result.payable) }) : t("discount.result", { discount: formatEur(result.discount), payable: formatEur(result.payable) })}
        </p>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
