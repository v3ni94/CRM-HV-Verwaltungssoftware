"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { localTotals, parseDecimal } from "./money";

/** Invoice draft for Lexware Office from the CRM (INT-LEXO-01): the invoice kind selects the
 *  issuing legal entity, amounts are decimal strings, the platform preview shows control sums
 *  and the queued draft is completed in Lexware Office (no finalize). Nothing is created
 *  before the explicit submit click. */

export type InvoiceKind = "broker" | "consulting" | "management";
type TaxType = "net" | "gross" | "vatfree";
type TaxRate = 0 | 7 | 19;
type ShippingType = "none" | "service" | "serviceperiod";

type Line = { name: string; description: string; quantity: string; unit_name: string; unit_price: string; tax_rate_percent: TaxRate };

export type DraftPreview = {
  config_id: string;
  legal_entity_id: string | null;
  legal_entity_name: string | null;
  payload: Record<string, unknown>;
  address_from_link: boolean;
  net: string;
  tax: string;
  gross: string;
  note: string;
};

export type DraftOut = { id: string; status: string; deeplink: string | null; last_error: string | null };

const KINDS: InvoiceKind[] = ["broker", "consulting", "management"];
const TAX_TYPES: TaxType[] = ["net", "gross", "vatfree"];
const TAX_RATES: TaxRate[] = [0, 7, 19];
const SHIPPING: ShippingType[] = ["none", "service", "serviceperiod"];

const emptyLine = (): Line => ({ name: "", description: "", quantity: "1", unit_name: "Stück", unit_price: "", tax_rate_percent: 19 });

export function LexofficeInvoiceDraftForm({
  contactId,
  contactName,
  onClose,
}: {
  contactId: string | null;
  contactName?: string | null;
  onClose?: () => void;
}) {
  const t = useTranslations("Lexoffice.draft");
  const [kind, setKind] = useState<InvoiceKind>("management");
  const [voucherDate, setVoucherDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [taxType, setTaxType] = useState<TaxType>("net");
  const [lines, setLines] = useState<Line[]>([emptyLine()]);
  const [shipping, setShipping] = useState<ShippingType>("none");
  const [serviceDate, setServiceDate] = useState("");
  const [serviceEnd, setServiceEnd] = useState("");
  const [title, setTitle] = useState("");
  const [introduction, setIntroduction] = useState("");
  const [remark, setRemark] = useState("");
  const [preview, setPreview] = useState<DraftPreview | null>(null);
  const [created, setCreated] = useState<DraftOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = useMemo(
    () =>
      lines.map((line) => ({
        ...line,
        quantityValue: parseDecimal(line.quantity, 4),
        priceValue: parseDecimal(line.unit_price, 4),
      })),
    [lines],
  );
  const lineErrors = parsed.map((line) => {
    if (!line.name.trim()) return t("missingName");
    if (line.quantityValue === null || line.quantityValue.startsWith("-") || Number(line.quantityValue) === 0) return t("invalidQuantity");
    if (line.priceValue === null) return t("invalidAmount");
    return null;
  });
  const vatfreeViolation = taxType === "vatfree" && lines.some((l) => l.tax_rate_percent !== 0);
  const shippingInvalid = (shipping !== "none" && !serviceDate) || (shipping === "serviceperiod" && !serviceEnd);
  const valid = lineErrors.every((e) => e === null) && !vatfreeViolation && !shippingInvalid && Boolean(voucherDate);

  const totals = valid
    ? localTotals(
        taxType,
        parsed.map((l) => ({ quantity: l.quantityValue ?? "0", unit_price: l.priceValue ?? "0", tax_rate_percent: l.tax_rate_percent })),
      )
    : null;

  function body() {
    return {
      invoice_kind: kind,
      contact_id: contactId,
      voucher_date: voucherDate,
      tax_type: taxType,
      line_items: parsed.map((l) => ({
        name: l.name.trim(),
        description: l.description.trim() || null,
        quantity: l.quantityValue,
        unit_name: l.unit_name.trim() || "Stück",
        unit_price: l.priceValue,
        tax_rate_percent: l.tax_rate_percent,
      })),
      shipping: { type: shipping, date: shipping === "none" ? null : serviceDate, end_date: shipping === "serviceperiod" ? serviceEnd : null },
      title: title.trim() || null,
      introduction: introduction.trim() || null,
      remark: remark.trim() || null,
    };
  }

  async function runPreview() {
    setBusy(true);
    setError(null);
    const res = await bff<DraftPreview>("/api/bff/integrations/lexoffice/invoice-drafts/preview", { method: "POST", body: JSON.stringify(body()) });
    setBusy(false);
    if (res.ok) setPreview(res.data);
    else setError(res.message);
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const res = await bff<DraftOut>("/api/bff/integrations/lexoffice/invoice-drafts", { method: "POST", body: JSON.stringify(body()) });
    setBusy(false);
    if (res.ok) setCreated(res.data);
    else setError(res.message);
  }

  function updateLine(index: number, patch: Partial<Line>) {
    setPreview(null);
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-3`} data-testid="lexoffice-draft-form">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t("heading")}</h3>
        {onClose ? (
          <button type="button" className={ui.buttonSm} onClick={onClose}>
            {t("close")}
          </button>
        ) : null}
      </div>
      <p className="text-xs text-muted">{t("intro")}</p>
      {created ? (
        <p className={ui.success} data-testid="lexoffice-draft-created">
          {t("queued")}{" "}
          {created.deeplink ? (
            <a href={created.deeplink} target="_blank" rel="noreferrer" className="font-medium hover:underline">
              {t("openDraft")}
            </a>
          ) : null}
        </p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("kind")}</span>
              <select className={ui.input} value={kind} onChange={(e) => { setPreview(null); setKind(e.target.value as InvoiceKind); }}>
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`kinds.${k}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("voucherDate")}</span>
              <input type="date" className={ui.input} value={voucherDate} onChange={(e) => { setPreview(null); setVoucherDate(e.target.value); }} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("taxType")}</span>
              <select className={ui.input} value={taxType} onChange={(e) => { setPreview(null); setTaxType(e.target.value as TaxType); }}>
                {TAX_TYPES.map((x) => (
                  <option key={x} value={x}>
                    {t(`taxTypes.${x}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="text-xs text-muted">
            {t("contact")}: {contactId ? (contactName ?? contactId) : t("noContact")}
          </p>
          {vatfreeViolation ? <p className={ui.error}>{t("vatfreeHint")}</p> : null}

          <fieldset className="flex flex-col gap-2">
            <legend className={ui.label}>{t("positions")}</legend>
            {lines.map((line, index) => (
              <div key={index} className="grid gap-2 rounded-md border border-border p-2 sm:grid-cols-6" data-testid="lexoffice-draft-line">
                <label className="flex flex-col gap-1 sm:col-span-2">
                  <span className={ui.label}>{t("name")}</span>
                  <input className={ui.input} value={line.name} onChange={(e) => updateLine(index, { name: e.target.value })} maxLength={255} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("quantity")}</span>
                  <input className={ui.input} inputMode="decimal" value={line.quantity} onChange={(e) => updateLine(index, { quantity: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("unit")}</span>
                  <input className={ui.input} value={line.unit_name} onChange={(e) => updateLine(index, { unit_name: e.target.value })} maxLength={50} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("unitPrice")}</span>
                  <input className={ui.input} inputMode="decimal" value={line.unit_price} placeholder="0,00" onChange={(e) => updateLine(index, { unit_price: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("taxRate")}</span>
                  <select className={ui.input} value={line.tax_rate_percent} onChange={(e) => updateLine(index, { tax_rate_percent: Number(e.target.value) as TaxRate })}>
                    {TAX_RATES.map((r) => (
                      <option key={r} value={r}>
                        {r} %
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1 sm:col-span-5">
                  <span className={ui.label}>{t("description")}</span>
                  <input className={ui.input} value={line.description} onChange={(e) => updateLine(index, { description: e.target.value })} maxLength={2000} />
                </label>
                <div className="flex items-end justify-between gap-2">
                  {lineErrors[index] ? <span className={ui.error}>{lineErrors[index]}</span> : <span />}
                  {lines.length > 1 ? (
                    <button type="button" className={ui.buttonSm} onClick={() => { setPreview(null); setLines((prev) => prev.filter((_, i) => i !== index)); }}>
                      {t("removePosition")}
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
            <div>
              <button type="button" className={ui.buttonSm} disabled={lines.length >= 300} onClick={() => setLines((prev) => [...prev, emptyLine()])}>
                {t("addPosition")}
              </button>
            </div>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("shipping")}</span>
              <select className={ui.input} value={shipping} onChange={(e) => { setPreview(null); setShipping(e.target.value as ShippingType); }}>
                {SHIPPING.map((x) => (
                  <option key={x} value={x}>
                    {t(`shippingTypes.${x}`)}
                  </option>
                ))}
              </select>
            </label>
            {shipping !== "none" ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("serviceDate")}</span>
                <input type="date" className={ui.input} value={serviceDate} onChange={(e) => { setPreview(null); setServiceDate(e.target.value); }} />
              </label>
            ) : null}
            {shipping === "serviceperiod" ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("serviceEnd")}</span>
                <input type="date" className={ui.input} value={serviceEnd} onChange={(e) => { setPreview(null); setServiceEnd(e.target.value); }} />
              </label>
            ) : null}
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("title")}</span>
            <input className={ui.input} value={title} maxLength={25} onChange={(e) => { setPreview(null); setTitle(e.target.value); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("introduction")}</span>
            <textarea className={ui.input} rows={2} value={introduction} maxLength={2000} onChange={(e) => { setPreview(null); setIntroduction(e.target.value); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("remark")}</span>
            <textarea className={ui.input} rows={2} value={remark} maxLength={2000} onChange={(e) => { setPreview(null); setRemark(e.target.value); }} />
          </label>

          {totals ? (
            <dl className="grid grid-cols-3 gap-2 text-sm" data-testid="lexoffice-draft-local-sums" aria-label={t("localSums")}>
              <div>
                <dt className={ui.label}>{t("net")}</dt>
                <dd className={ui.num}>{totals.net}</dd>
              </div>
              <div>
                <dt className={ui.label}>{t("tax")}</dt>
                <dd className={ui.num}>{totals.tax}</dd>
              </div>
              <div>
                <dt className={ui.label}>{t("gross")}</dt>
                <dd className={ui.num}>{totals.gross}</dd>
              </div>
            </dl>
          ) : null}

          {preview ? (
            <div className={ui.notice} data-testid="lexoffice-draft-preview">
              <p className="font-medium">{t("previewHeading")}</p>
              <p>
                {t("legalEntity")}: {preview.legal_entity_name ?? preview.config_id}
              </p>
              <p>
                {t("net")} {preview.net}, {t("tax")} {preview.tax}, {t("gross")} {preview.gross}
              </p>
              <p>{preview.address_from_link ? t("addressFromLink") : t("addressFromText")}</p>
              <p className="text-xs">{preview.note}</p>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.button} disabled={!valid || busy} onClick={() => void runPreview()}>
              {t("preview")}
            </button>
            <button type="button" className={ui.primary} disabled={!valid || busy || !preview} onClick={() => void submit()}>
              {t("submit")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
