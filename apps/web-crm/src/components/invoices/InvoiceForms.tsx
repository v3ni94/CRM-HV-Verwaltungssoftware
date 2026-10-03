"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { EMPTY_FACTUAL_LINKS, InvoiceFactualLinks, type FactualLinks } from "@/components/invoices/InvoiceFactualLinks";
import { InvoiceKindDeductions, type InvoiceKindValue } from "@/components/invoices/InvoiceKindDeductions";
import { EMPTY_LINE, InvoiceLinesEditor } from "@/components/invoices/InvoiceLinesEditor";
import { formatEur } from "@/lib/format";
import { centsToDecimal, parseCents } from "@/lib/money";
import { checkSplitSum, type Deduction, type EntryLine } from "@/lib/invoice-lines";
import { useRefreshAfterPost } from "@/lib/useRefreshAfterPost";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
type LedgerOption = Option & { legalEntityId?: string | null };
const MONEY = /^\d+([.,]\d{1,2})?$/;
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
// GAM-710: integer cents without a binary float; the API receives "1234.50".
const cents = (v: string) => {
  const c = parseCents(v);
  return c === null ? NaN : Number(c);
};
const fmt = (c: number) => centsToDecimal(BigInt(Math.trunc(c)));

/** Incoming invoice with one line (M14). Findings are hints; the review status stays open. */
export function InvoiceCreate({ ledgers, accounts }: { ledgers: LedgerOption[]; accounts: Record<string, Option[]> }) {
  const t = useTranslations("Invoices");
  const router = useRouter();
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  // M14-02: Verknüpfungen für die sachliche Prüfung (Auftrag, Beschluss, Planposition, Rechnungsplan).
  const [links, setLinks] = useState<FactualLinks>(EMPTY_FACTUAL_LINKS);
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<Option[]>([]);
  const [provider, setProvider] = useState("");
  const [f, setF] = useState({ number: "", invoice_date: "", service_from: "", net: "", vat_percent: "19", account: "", order_reference: "", recipient_name: "" });
  // M14-01/04/05: optionale Angaben zur Prüfung am Beleg (Leistungsort, Aussteller, Einbehalte).
  const [x, setX] = useState({ service_to: "", service_place: "", issuer_vat_id: "", issuer_tax_number: "", prepaid_amount: "", retention_amount: "", discount_percent: "", discount_until: "", reverse_charge: false, construction_withholding: false, input_tax_deductible: "" });
  const xMoney = (v: string) => v.trim() === "" || MONEY.test(v.trim());
  const xValid = xMoney(x.prepaid_amount) && xMoney(x.retention_amount) && xMoney(x.discount_percent);
  // Anlagen zum Beleg (Q02, 7.9.1 PÜ01): Dokument-IDs aus dem DMS, getrennt durch Leerzeichen, Komma oder Zeilenumbruch.
  const [attachments, setAttachments] = useState("");
  const attachmentIds = attachments.split(/[\s,;]+/).filter(Boolean);
  const attachmentsValid = attachmentIds.length <= 50 && attachmentIds.every((v) => UUID.test(v)) && new Set(attachmentIds).size === attachmentIds.length;
  // GAM-105: Rechnungsart und Abzug gebuchter Abschläge; GAM-106: Aufteilung auf mehrere Zeilen.
  const [kind, setKind] = useState<InvoiceKindValue>("invoice");
  const [deductions, setDeductions] = useState<Deduction[]>([]);
  const [split, setSplit] = useState(false);
  const [splitLines, setSplitLines] = useState<EntryLine[]>([{ ...EMPTY_LINE }, { ...EMPTY_LINE }]);
  const [splitGross, setSplitGross] = useState("");
  const xNum = (v: string) => (v.trim() === "" ? null : v.trim().replace(",", "."));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((p) => ({ ...p, [k]: e.target.value }));
  const search = async () => {
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}`);
    if (res.ok) setProviders(res.data.items.map((c) => ({ id: c.id, label: c.display_name })));
  };
  const net = MONEY.test(f.net) ? cents(f.net) : NaN;
  const vat = Number.isFinite(net) ? Math.round((net * Number(f.vat_percent)) / 100) : NaN;
  const splitCheck = checkSplitSum(splitLines, splitGross);
  const splitReady = splitCheck.ok && splitLines.every((l) => l.account_id && l.text.trim().length >= 3);
  const headNet = split ? Number(splitCheck.totals?.net ?? 0n) : net;
  const headVat = split ? Number(splitCheck.totals?.vat ?? 0n) : vat;
  const finalGross = split ? splitGross : Number.isFinite(net) ? fmt(net + vat) : "";
  const baseValid = xValid && attachmentsValid && ledger && provider && f.number.trim() && f.invoice_date;
  const valid = baseValid && (split ? splitReady : Number.isFinite(net) && f.account);
  const submit = async () => {
    setBusy(true);
    setError(null);
    const body = {
      ledger_id: ledger,
      provider_contact_id: provider,
      number: f.number.trim(),
      invoice_date: f.invoice_date,
      service_from: f.service_from || null,
      kind,
      deductions: kind === "final" ? deductions : [],
      net: fmt(headNet),
      vat: fmt(headVat),
      gross: fmt(headNet + headVat),
      order_reference: f.order_reference.trim() || null,
      recipient_name: f.recipient_name.trim() || null,
      service_to: x.service_to || null,
      attachment_document_ids: attachmentIds,
      work_order_id: links.work_order_id || null,
      resolution_id: links.resolution_id || null,
      plan_item_id: links.plan_item_id || null,
      recurring_plan_id: links.recurring_plan_id || null,
      service_place: x.service_place.trim() || null,
      issuer_vat_id: x.issuer_vat_id.trim() || null,
      issuer_tax_number: x.issuer_tax_number.trim() || null,
      prepaid_amount: xNum(x.prepaid_amount),
      retention_amount: xNum(x.retention_amount),
      discount_percent: xNum(x.discount_percent),
      discount_until: x.discount_until || null,
      reverse_charge: x.reverse_charge,
      construction_withholding: x.construction_withholding,
      input_tax_deductible: x.input_tax_deductible === "" ? null : x.input_tax_deductible === "yes",
      lines: split
        ? splitLines.map((l) => {
            const n = checkSplitSum([l], "0").totals;
            return { account_id: l.account_id, net: centsToDecimal(n?.net ?? 0n), vat_percent: l.vat_percent, vat: centsToDecimal(n?.vat ?? 0n), text: l.text.trim() };
          })
        : [{ account_id: f.account, net: fmt(net), vat_percent: f.vat_percent, vat: fmt(vat), text: f.number.trim() }],
    };
    const res = await bff<{ id: string }>("/api/bff/accounting/invoices", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.push(`/rechnungen/${res.data.id}`);
    else setError(res.message);
  };
  const field = (k: keyof typeof f, type = "text") => (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t(`fields.${k}`)}</span>
      <input className={ui.input} type={type} value={f[k]} onChange={set(k)} />
    </label>
  );
  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.ledger")}</span>
          <select className={ui.input} value={ledger} onChange={(e) => { setLedger(e.target.value); setF((p) => ({ ...p, account: "" })); }}>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>{l.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.provider_search")}</span>
          <span className="flex gap-1">
            <input className={ui.input} value={q} onChange={(e) => setQ(e.target.value)} />
            <button type="button" className={ui.button} onClick={search} disabled={q.trim().length < 2}>{t("search")}</button>
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.provider")}</span>
          <select className={ui.input} value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">{t("choose")}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </label>
        {field("number")}
        {field("invoice_date", "date")}
        {field("service_from", "date")}
        {split ? null : field("net")}
        {split ? null : <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.vat_percent")}</span>
          <select className={ui.input} value={f.vat_percent} onChange={set("vat_percent")}>
            {["19", "7", "0"].map((v) => (
              <option key={v} value={v}>{v} %</option>
            ))}
          </select>
        </label>}
        {split ? null : <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.account")}</span>
          <select className={ui.input} value={f.account} onChange={set("account")}>
            <option value="">{t("choose")}</option>
            {(accounts[ledger] ?? []).map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </label>}
        {field("order_reference")}
        {field("recipient_name")}
      </div>
      <InvoiceKindDeductions
        ledgerId={ledger}
        providerId={provider}
        kind={kind}
        finalGross={finalGross}
        deductions={deductions}
        onKind={setKind}
        onDeductions={setDeductions}
      />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} />
        {t("split.toggle")}
      </label>
      {split ? <InvoiceLinesEditor accounts={accounts[ledger] ?? []} lines={splitLines} documentGross={splitGross} onLines={setSplitLines} onDocumentGross={setSplitGross} /> : null}
      <details data-testid="invoice-extra">
        <summary className="cursor-pointer text-sm font-medium">{t("extra.title")}</summary>
        <p className={ui.help}>{t("extra.hint")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-4">
          {(["service_to", "discount_until"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1">
              <span className={ui.label}>{t(`extra.${k}`)}</span>
              <input className={ui.input} type="date" value={x[k]} onChange={(e) => setX((p) => ({ ...p, [k]: e.target.value }))} />
            </label>
          ))}
          {(["service_place", "issuer_vat_id", "issuer_tax_number", "prepaid_amount", "retention_amount", "discount_percent"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1">
              <span className={ui.label}>{t(`extra.${k}`)}</span>
              <input className={ui.input} value={x[k]} onChange={(e) => setX((p) => ({ ...p, [k]: e.target.value }))} />
            </label>
          ))}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("extra.input_tax_deductible")}</span>
            <select className={ui.input} value={x.input_tax_deductible} onChange={(e) => setX((p) => ({ ...p, input_tax_deductible: e.target.value }))}>
              <option value="">{t("extra.unknown")}</option>
              <option value="yes">{t("extra.yes")}</option>
              <option value="no">{t("extra.no")}</option>
            </select>
          </label>
          {(["reverse_charge", "construction_withholding"] as const).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={x[k]} onChange={(e) => setX((p) => ({ ...p, [k]: e.target.checked }))} />
              {t(`extra.${k}`)}
            </label>
          ))}
        </div>
        <label className="mt-2 flex flex-col gap-1">
          <span className={ui.label}>{t("extra.attachment_document_ids")}</span>
          <textarea className={ui.input} rows={2} value={attachments} onChange={(e) => setAttachments(e.target.value)} aria-invalid={!attachmentsValid} data-testid="attachment-ids" />
          <span className={ui.help}>{attachmentsValid ? t("extra.attachment_hint", { count: attachmentIds.length }) : t("extra.attachment_invalid")}</span>
        </label>
      </details>
      <InvoiceFactualLinks
        ledgerId={ledger}
        legalEntityId={ledgers.find((l) => l.id === ledger)?.legalEntityId ?? null}
        providerId={provider}
        value={links}
        onChange={setLinks}
      />
      <p className="text-sm text-muted" data-testid="gross">
        {split ? "" : Number.isFinite(net) ? t("gross", { gross: formatEur(fmt(net + vat)), vat: formatEur(fmt(vat)) }) : ""}
      </p>
      <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={submit} disabled={busy || !valid}>{t("create")}</button>
      {!valid ? <p className={ui.help}>{t("requiredHint")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

/** Review steps (PÜ05), IBAN confirmation, release by a second person and posting. */
export function InvoiceActions({ id, reviewStatus, postingStatus, released, ibanOpen, revision = "" }: { id: string; reviewStatus: string; postingStatus: string; released: boolean; ibanOpen: boolean; revision?: string }) {
  const t = useTranslations("Invoices");
  const [step, setStep] = useState("completeness");
  const [result, setResult] = useState("ok");
  const [reason, setReason] = useState("");
  const [posting, setBusy] = useState(false);
  // Buttons stay disabled until the server component has re-rendered (see useRefreshAfterPost).
  const { refreshing, refresh } = useRefreshAfterPost(revision);
  const busy = posting || refreshing;
  const [error, setError] = useState<string | null>(null);
  const post = async (path: string, body?: unknown, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return false;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/invoices/${id}/${path}`, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (res.ok) refresh();
    else setError(res.message);
    return res.ok;
  };
  if (postingStatus !== "unposted") return null;
  const closed = reviewStatus === "closed_ok" || reviewStatus === "closed_with_reservation";
  // Der nächste Schritt wird benannt, damit kein Button fehlt, ohne dass klar ist, warum.
  const nextStep = released ? "post" : closed ? "release" : ibanOpen ? "iban" : "review";
  return (
    <div className="flex flex-col gap-3">
      <p className={ui.help} data-testid="invoice-next-step">
        {t(`nextStep.${nextStep}`)}
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("step")}</span>
          <select className={ui.input} value={step} onChange={(e) => setStep(e.target.value)}>
            {["completeness", "factual", "arithmetic_tax"].map((s) => (
              <option key={s} value={s}>{t(`steps.${s}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("result")}</span>
          <select className={ui.input} value={result} onChange={(e) => setResult(e.target.value)}>
            {["ok", "reservation", "query", "objected"].map((r) => (
              <option key={r} value={r}>{t(`results.${r}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("reason")}</span>
          <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button
          type="button"
          className={ui.button}
          disabled={busy || reason.trim().length < 3}
          onClick={async () => {
            if (await post("reviews", { step, result, reason: reason.trim() })) setReason("");
          }}
        >
          {t("recordStep")}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {ibanOpen ? (
          <button type="button" className={ui.button} disabled={busy} onClick={() => post("confirm-iban", undefined, t("confirmIban"))}>
            {t("confirmIbanButton")}
          </button>
        ) : null}
        {closed && !released ? (
          <button type="button" className={ui.primary} disabled={busy} onClick={() => post("release")}>{t("release")}</button>
        ) : null}
        {released ? (
          <button type="button" className={ui.primary} disabled={busy} onClick={() => post("post", undefined, t("confirmPost"))}>{t("post")}</button>
        ) : null}
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
