"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { AMOUNT_REASONS, type AmountReason, type AmountRow, amountsValidOn, findOverlap, grossFromNet, monthlyTotal, parseAmount, type PaymentTypeOption, sortAmounts, withNewAmount } from "./amounts";

/** Draft of an amount in the create form: recorded after POST /contracts from the start date. */
export type AmountDraft = { payment_type_code: string; net: string; vat_percent: string };

export function amountDraftBody(draft: AmountDraft, validFrom: string): { payment_type_code: string; net: string; vat_percent: string; gross: string; valid_from: string; valid_to: null; reason: AmountReason } | null {
  const net = parseAmount(draft.net, { allowNegative: true });
  const vat = normaliseVat(draft.vat_percent);
  if (net === null || vat === null) return null;
  return { payment_type_code: draft.payment_type_code, net, vat_percent: vat, gross: grossFromNet(net, vat), valid_from: validFrom, valid_to: null, reason: "initial" };
}

/** "19" | "7,0" | "" -> "19" | "7.0" | "0"; null when not a percentage 0..100. */
export function normaliseVat(raw: string): string | null {
  const value = raw.trim().replace(",", ".") || "0";
  if (!/^\d{1,3}(\.\d{1,8})?$/.test(value) || Number(value) > 100) return null;
  return value;
}

function typeLabel(types: PaymentTypeOption[], code: string): string {
  return types.find((t) => t.code === code)?.label ?? code;
}

/** Several amounts with kind, net and VAT for the create form (valid from the contract start). */
export function AmountsDraftFields({ drafts, onChange, paymentTypes, errors }: { drafts: AmountDraft[]; onChange: (drafts: AmountDraft[]) => void; paymentTypes: PaymentTypeOption[]; errors: Record<number, string> }) {
  const t = useTranslations("contracts");
  const update = (index: number, patch: Partial<AmountDraft>) => onChange(drafts.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  return (
    <div className="flex flex-col gap-3" data-testid="amount-drafts">
      {drafts.map((draft, index) => {
        const net = parseAmount(draft.net, { allowNegative: true });
        const vat = normaliseVat(draft.vat_percent);
        return (
          <div key={index} className="grid gap-3 sm:grid-cols-4" data-testid={`amount-draft-${index}`}>
            <label className={ui.label}>
              {t("amounts.kind")}
              <select className={ui.input} value={draft.payment_type_code} onChange={(e) => update(index, { payment_type_code: e.target.value })}>
                {paymentTypes.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label className={ui.label}>
              {t("amounts.net")}
              <input className={ui.input} inputMode="decimal" placeholder="1.234,56" value={draft.net} onChange={(e) => update(index, { net: e.target.value })} />
            </label>
            <label className={ui.label}>
              {t("amounts.vat")}
              <input className={ui.input} inputMode="decimal" value={draft.vat_percent} onChange={(e) => update(index, { vat_percent: e.target.value })} />
            </label>
            <div className="flex items-end justify-between gap-2 text-sm">
              <span data-testid={`amount-draft-gross-${index}`}>{net !== null && vat !== null ? `${t("amounts.gross")}: ${formatEur(grossFromNet(net, vat))}` : t("amounts.grossPending")}</span>
              <button type="button" className={ui.buttonSm} onClick={() => onChange(drafts.filter((_, i) => i !== index))}>
                {t("amounts.remove")}
              </button>
            </div>
            {errors[index] ? (
              <span role="alert" className={`${ui.error} sm:col-span-4`}>
                {errors[index]}
              </span>
            ) : null}
          </div>
        );
      })}
      <div>
        <button type="button" className={ui.button} onClick={() => onChange([...drafts, { payment_type_code: paymentTypes[0]?.code ?? "rent", net: "", vat_percent: "0" }])} disabled={paymentTypes.length === 0}>
          {t("amounts.addRow")}
        </button>
        {paymentTypes.length === 0 ? <p className={ui.help}>{t("amounts.noTypes")}</p> : null}
      </div>
    </div>
  );
}

/**
 * Sollbeträge des Vertrags (Miete, Vorauszahlungen, Hausgeld, Rücklage, ...): history with
 * period, current total per month and a form for a new amount from a date. A new amount of a
 * kind closes the open previous amount the day before (API rule); the past is never
 * overwritten. Recording an amount posts nothing: receivables come from the manual
 * Sollstellungslauf, statements stay behind G3.
 */
export function AmountsPanel({
  contractId,
  amounts,
  paymentTypes,
  canUpdate,
  startDate,
  endDate,
}: {
  contractId: string;
  amounts: AmountRow[];
  paymentTypes: PaymentTypeOption[];
  canUpdate: boolean;
  startDate: string;
  endDate: string | null;
}) {
  const t = useTranslations("contracts");
  const router = useRouter();
  const today = new Date().toISOString().slice(0, 10);
  const defaultFrom = today < startDate ? startDate : endDate && today > endDate ? startDate : today;
  const [rows, setRows] = useState(() => sortAmounts(amounts));
  const [asOfInput, setAsOf] = useState(defaultFrom);
  const asOf = asOfInput || defaultFrom;
  const [code, setCode] = useState(paymentTypes[0]?.code ?? "");
  const [net, setNet] = useState("");
  const [vat, setVat] = useState("0");
  const [validFrom, setValidFrom] = useState(defaultFrom);
  const [validTo, setValidTo] = useState("");
  const [reason, setReason] = useState<AmountReason>("initial");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const parsedNet = parseAmount(net, { allowNegative: true });
  const parsedVat = normaliseVat(vat);
  const gross = parsedNet !== null && parsedVat !== null ? grossFromNet(parsedNet, parsedVat) : null;
  const current = amountsValidOn(rows, asOf);
  const currentIds = new Set(current.map((r) => r.id));

  function pickKind(next: string) {
    setCode(next);
    // Default reason: first amount of the kind is the initial one, later ones a change.
    setReason(rows.some((r) => r.payment_type_code === next) ? "increase" : "initial");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!code || !validFrom) return setError(t("amounts.errors.required"));
    if (parsedNet === null) return setError(t("amounts.errors.amount"));
    if (parsedVat === null) return setError(t("amounts.errors.vat"));
    if (validFrom < startDate || (endDate && validFrom > endDate)) return setError(t("amounts.errors.validFromRange", { start: formatDate(startDate), end: endDate ? formatDate(endDate) : t("amounts.open") }));
    if (validTo && validTo < validFrom) return setError(t("amounts.errors.validToOrder"));
    const conflict = findOverlap(rows, { payment_type_code: code, valid_from: validFrom, valid_to: validTo || null });
    if (conflict) {
      return setError(t("amounts.errors.overlap", { kind: typeLabel(paymentTypes, conflict.payment_type_code), from: formatDate(conflict.valid_from), to: conflict.valid_to ? formatDate(conflict.valid_to) : t("amounts.open") }));
    }
    setBusy(true);
    const res = await bff<AmountRow>(`/api/bff/contracts/${contractId}/payments`, {
      method: "POST",
      body: JSON.stringify({ payment_type_code: code, net: parsedNet, vat_percent: parsedVat, gross, valid_from: validFrom, valid_to: validTo || null, reason }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setRows((prev) => withNewAmount(prev, res.data));
    setNet("");
    setValidTo("");
    router.refresh();
  }

  return (
    <section className={ui.card} data-testid="contract-amounts">
      <h2 className={ui.h2}>{t("amounts.title")}</h2>
      <p className={ui.help}>{t("amounts.help")}</p>
      <div className="mt-3 flex flex-wrap items-end gap-3" data-testid="amounts-total">
        <label className={ui.label}>
          {t("amounts.asOf")}
          <input className={ui.input} type="date" value={asOfInput} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <p className="text-sm">
          {t("amounts.total", { count: current.length })}: <strong className={ui.num}>{formatEur(monthlyTotal(rows, asOf))}</strong>
        </p>
      </div>
      {rows.length === 0 ? (
        <p className={`${ui.help} mt-3`}>{t("amounts.none")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={`${ui.table} mt-3`}>
            <thead>
              <tr>
                <th>{t("amounts.kind")}</th>
                <th>{t("amounts.net")}</th>
                <th>{t("amounts.vat")}</th>
                <th>{t("amounts.gross")}</th>
                <th>{t("amounts.validFrom")}</th>
                <th>{t("amounts.validTo")}</th>
                <th>{t("amounts.reason")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-testid={currentIds.has(r.id) ? "amount-row-current" : "amount-row"}>
                  <td>
                    {typeLabel(paymentTypes, r.payment_type_code)}
                    {currentIds.has(r.id) ? <span className={`${ui.badgeSuccess} ml-2`}>{t("amounts.current")}</span> : null}
                  </td>
                  <td className={ui.num}>{formatEur(r.net)}</td>
                  <td className={ui.num}>{formatDecimal(r.vat_percent, 2)} %</td>
                  <td className={ui.num}>{formatEur(r.gross)}</td>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{r.valid_to ? formatDate(r.valid_to) : t("amounts.open")}</td>
                  <td>{t(`amounts.reasons.${r.reason}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canUpdate && paymentTypes.length > 0 ? (
        <form onSubmit={submit} className="mt-4 grid gap-3 sm:grid-cols-4" noValidate data-testid="amount-form">
          <p className={`${ui.help} sm:col-span-4`}>{t("amounts.formHelp")}</p>
          <label className={ui.label}>
            {t("amounts.kind")}
            <select className={ui.input} value={code} onChange={(e) => pickKind(e.target.value)}>
              {paymentTypes.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className={ui.label}>
            {t("amounts.net")}
            <input className={ui.input} inputMode="decimal" placeholder="1.234,56" value={net} onChange={(e) => setNet(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("amounts.vat")}
            <input className={ui.input} inputMode="decimal" value={vat} onChange={(e) => setVat(e.target.value)} />
          </label>
          <p className="flex items-end text-sm" data-testid="amount-gross">
            {gross !== null ? `${t("amounts.gross")}: ${formatEur(gross)}` : t("amounts.grossPending")}
          </p>
          <label className={ui.label}>
            {t("amounts.validFrom")}
            <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("amounts.validTo")}
            <input className={ui.input} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
          </label>
          <label className={ui.label}>
            {t("amounts.reason")}
            <select className={ui.input} value={reason} onChange={(e) => setReason(e.target.value as AmountReason)}>
              {AMOUNT_REASONS.map((r) => (
                <option key={r} value={r}>
                  {t(`amounts.reasons.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("amounts.add")}
            </button>
          </div>
          {error ? (
            <p role="alert" className={`${ui.alert} sm:col-span-4`}>
              {error}
            </p>
          ) : null}
        </form>
      ) : canUpdate ? (
        <p className={`${ui.help} mt-3`}>{t("amounts.noTypes")}</p>
      ) : null}
    </section>
  );
}
