"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
const MONEY = /^\d+([.,]\d{1,2})?$/;
const cents = (v: string) => Math.round(Number(v.replace(",", ".")) * 100);
const fmt = (c: number) => (c / 100).toFixed(2);

/** Incoming invoice with one line (M14). Findings are hints; the review status stays open. */
export function InvoiceCreate({ ledgers, accounts }: { ledgers: Option[]; accounts: Record<string, Option[]> }) {
  const t = useTranslations("Invoices");
  const router = useRouter();
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<Option[]>([]);
  const [provider, setProvider] = useState("");
  const [f, setF] = useState({ number: "", invoice_date: "", service_from: "", net: "", vat_percent: "19", account: "", order_reference: "", recipient_name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((p) => ({ ...p, [k]: e.target.value }));
  const search = async () => {
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}`);
    if (res.ok) setProviders(res.data.items.map((c) => ({ id: c.id, label: c.display_name })));
  };
  const net = MONEY.test(f.net) ? cents(f.net) : NaN;
  const vat = Number.isFinite(net) ? Math.round((net * Number(f.vat_percent)) / 100) : NaN;
  const valid = ledger && provider && f.number.trim() && f.invoice_date && Number.isFinite(net) && f.account;
  const submit = async () => {
    setBusy(true);
    setError(null);
    const body = {
      ledger_id: ledger,
      provider_contact_id: provider,
      number: f.number.trim(),
      invoice_date: f.invoice_date,
      service_from: f.service_from || null,
      net: fmt(net),
      vat: fmt(vat),
      gross: fmt(net + vat),
      order_reference: f.order_reference.trim() || null,
      recipient_name: f.recipient_name.trim() || null,
      lines: [{ account_id: f.account, net: fmt(net), vat_percent: f.vat_percent, vat: fmt(vat), text: f.number.trim() }],
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
        {field("net")}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.vat_percent")}</span>
          <select className={ui.input} value={f.vat_percent} onChange={set("vat_percent")}>
            {["19", "7", "0"].map((v) => (
              <option key={v} value={v}>{v} %</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("fields.account")}</span>
          <select className={ui.input} value={f.account} onChange={set("account")}>
            <option value="">{t("choose")}</option>
            {(accounts[ledger] ?? []).map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </label>
        {field("order_reference")}
        {field("recipient_name")}
      </div>
      <p className="text-sm text-muted" data-testid="gross">
        {Number.isFinite(net) ? t("gross", { gross: formatEur(fmt(net + vat)), vat: formatEur(fmt(vat)) }) : ""}
      </p>
      <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={submit} disabled={busy || !valid}>{t("create")}</button>
      {!valid ? <p className={ui.help}>{t("requiredHint")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

/** Review steps (PÜ05), IBAN confirmation, release by a second person and posting. */
export function InvoiceActions({ id, reviewStatus, postingStatus, released, ibanOpen }: { id: string; reviewStatus: string; postingStatus: string; released: boolean; ibanOpen: boolean }) {
  const t = useTranslations("Invoices");
  const router = useRouter();
  const [step, setStep] = useState("completeness");
  const [result, setResult] = useState("ok");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const post = async (path: string, body?: unknown, confirmText?: string) => {
    if (confirmText && !window.confirm(confirmText)) return false;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/invoices/${id}/${path}`, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.refresh();
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
