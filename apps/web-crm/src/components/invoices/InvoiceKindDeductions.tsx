"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { finalSummary, type Deduction } from "@/lib/invoice-lines";
import { ui } from "@/lib/ui";

export type InvoiceKindValue = "invoice" | "partial" | "final";
type Partial = { id: string; number: string; invoice_date: string; gross: string };

/**
 * GAM-105 (D12): invoice kind and deduction of booked partial invoices of the same issuer.
 * The API checks again (invoices.expense_amount); this shows service total, deduction and
 * remaining obligation before the entry is saved.
 */
export function InvoiceKindDeductions({
  ledgerId,
  providerId,
  kind,
  finalGross,
  deductions,
  onKind,
  onDeductions,
}: {
  ledgerId: string;
  providerId: string;
  kind: InvoiceKindValue;
  finalGross: string;
  deductions: Deduction[];
  onKind: (k: InvoiceKindValue) => void;
  onDeductions: (d: Deduction[]) => void;
}) {
  const t = useTranslations("Invoices");
  const [partials, setPartials] = useState<Partial[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (kind !== "final" || !ledgerId || !providerId) {
      setPartials(null);
      return;
    }
    let cancelled = false;
    const q = `filter[ledger_id]=${encodeURIComponent(ledgerId)}&filter[provider_contact_id]=${encodeURIComponent(providerId)}&filter[kind]=partial&filter[posting_status]=posted`;
    void bff<Partial[]>(`/api/bff/accounting/invoices?${q}`).then((res) => {
      if (cancelled) return;
      if (res.ok) {
        setPartials(res.data);
        setError(null);
      } else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [kind, ledgerId, providerId]);

  const selected = new Set(deductions.map((d) => d.invoice_id));
  const toggle = (p: Partial) =>
    onDeductions(selected.has(p.id) ? deductions.filter((d) => d.invoice_id !== p.id) : [...deductions, { invoice_id: p.id, gross: p.gross }]);
  const summary = kind === "final" ? finalSummary(finalGross, deductions) : null;

  return (
    <div className="flex flex-col gap-2" data-testid="invoice-kind">
      <label className="flex flex-col gap-1 sm:max-w-xs">
        <span className={ui.label}>{t("kind.label")}</span>
        <select
          className={ui.input}
          value={kind}
          onChange={(e) => {
            onKind(e.target.value as InvoiceKindValue);
            onDeductions([]);
          }}
        >
          {(["invoice", "partial", "final"] as const).map((k) => (
            <option key={k} value={k}>{t(`kind.${k}`)}</option>
          ))}
        </select>
      </label>
      {kind === "final" ? (
        <fieldset className="flex flex-col gap-1" data-testid="deduction-list">
          <legend className={ui.label}>{t("kind.deductionTitle")}</legend>
          {!providerId ? <p className={ui.help}>{t("kind.chooseProvider")}</p> : null}
          {providerId && partials !== null && partials.length === 0 ? <p className={ui.help}>{t("kind.noPartials")}</p> : null}
          {(partials ?? []).map((p) => (
            <label key={p.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p)} />
              {t("kind.partialRow", { number: p.number, date: p.invoice_date, gross: formatEur(p.gross) })}
            </label>
          ))}
          {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
          {summary ? (
            <p className="text-sm" data-testid="final-summary">
              {t("kind.summary", { service: formatEur(summary.service), deducted: formatEur(summary.deducted), remaining: formatEur(summary.remaining) })}
            </p>
          ) : null}
          {summary && !summary.ok ? <p role="alert" className={ui.alert}>{t("kind.deductionTooHigh")}</p> : null}
        </fieldset>
      ) : null}
    </div>
  );
}
