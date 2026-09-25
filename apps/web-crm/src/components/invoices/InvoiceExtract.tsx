"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  invoicePreview,
  isRunPending,
  POLL_INTERVAL_MS,
  type Conversation,
  type DocumentOut,
  type ImportRun,
  type InvoicePreview,
  type Proposal,
  type Run,
} from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Option = { id: string; label: string };
type Stage = "idle" | "picking" | "uploading" | "queued" | "processing" | "review" | "done";

type Form = {
  provider_contact_id: string;
  number: string;
  invoice_date: string;
  due_date: string;
  net: string;
  vat: string;
  gross: string;
  discount_percent: string;
  discount_until: string;
  order_reference: string;
  iban_confirm: string;
  account: string;
};

const EMPTY_FORM: Form = {
  provider_contact_id: "",
  number: "",
  invoice_date: "",
  due_date: "",
  net: "",
  vat: "",
  gross: "",
  discount_percent: "",
  discount_until: "",
  order_reference: "",
  iban_confirm: "",
  account: "",
};

function fromPreview(preview: InvoicePreview): Form {
  const inv = preview.invoice;
  return {
    ...EMPTY_FORM,
    provider_contact_id: preview.supplier_candidates[0]?.contact_id ?? "",
    number: inv.invoice_number ?? "",
    invoice_date: inv.invoice_date ?? "",
    due_date: inv.due_date ?? "",
    net: inv.net ?? "",
    vat: inv.vat ?? "",
    gross: inv.gross ?? "",
    discount_percent: inv.discount_percent ?? "",
    discount_until: inv.discount_until ?? "",
    order_reference: inv.order_reference ?? "",
  };
}

/** "Aus Dokument erfassen" (M14): upload a document, run extract_invoice, then a fully editable
 * review form before the invoice is created as a draft. Nothing here is applied automatically:
 * the reviewer fills the ledger, the payee, the IBAN (never taken from the AI proposal, rule
 * 0.1.6) and the ledger account before "Als Entwurf anlegen". */
export function InvoiceExtract({
  ledgers,
  accounts,
  initialProposalId,
  onClose,
}: {
  ledgers: Option[];
  accounts: Record<string, Option[]>;
  initialProposalId?: string | null;
  onClose?: () => void;
}) {
  const t = useTranslations("Invoices");
  const router = useRouter();
  const [stage, setStage] = useState<Stage>(initialProposalId ? "processing" : "idle");
  const [loadedInitial, setLoadedInitial] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [q, setQ] = useState("");
  const [providers, setProviders] = useState<Option[]>([]);
  const [form, setForm] = useState<Form>(EMPTY_FORM);

  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }));

  const search = async () => {
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}`);
    if (res.ok) setProviders(res.data.items.map((c) => ({ id: c.id, label: c.display_name })));
  };

  const waitForRun = async (run: Run): Promise<Run> => {
    let current = run;
    setStage(current.status === "running" ? "processing" : "queued");
    while (isRunPending(current)) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const res = await bff<Run>(`/api/bff/ai/runs/${current.id}`);
      if (!res.ok) throw new Error(res.message);
      current = res.data;
      if (isRunPending(current)) setStage(current.status === "running" ? "processing" : "queued");
    }
    return current;
  };

  const startFromDocument = async (documentId: string) => {
    setError(null);
    try {
      const conv = await bff<Conversation>("/api/bff/ai/conversations", {
        method: "POST",
        body: JSON.stringify({ title: t("extract.button"), context_type: "global", context_id: null }),
      });
      if (!conv.ok) throw new Error(conv.message);
      const run = await bff<Run>(`/api/bff/ai/conversations/${conv.data.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: t("extract.button"), task: "extract_invoice", document_ids: [documentId] }),
      });
      if (!run.ok) throw new Error(run.message);
      const finished = await waitForRun(run.data);
      if (finished.status === "blocked") throw new Error(t("extract.blocked", { reason: finished.error ?? "" }));
      if (finished.status !== "succeeded") throw new Error(t("extract.failed", { reason: finished.error ?? "" }));
      if (!finished.proposal_id) throw new Error(t("extract.noProposal"));
      const prop = await bff<Proposal>(`/api/bff/ai/proposals/${finished.proposal_id}`);
      if (!prop.ok) throw new Error(prop.message);
      setProposal(prop.data);
      setForm(fromPreview(invoicePreview(prop.data.proposed)));
      setStage("review");
    } catch (err) {
      setError((err as Error).message);
      setStage("idle");
    }
  };

  const onFile = async (file: File) => {
    setStage("uploading");
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      body.set("title", file.name);
      const doc = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body });
      if (!doc.ok) throw new Error(doc.message);
      await startFromDocument(doc.data.id);
    } catch (err) {
      setError((err as Error).message);
      setStage("idle");
    }
  };

  useEffect(() => {
    if (!initialProposalId || loadedInitial) return;
    setLoadedInitial(true);
    void (async () => {
      const prop = await bff<Proposal>(`/api/bff/ai/proposals/${initialProposalId}`);
      if (!prop.ok) {
        setError(prop.message);
        setStage("idle");
        return;
      }
      setProposal(prop.data);
      setForm(fromPreview(invoicePreview(prop.data.proposed)));
      setStage("review");
    })();
  }, [initialProposalId, loadedInitial]);

  const preview = proposal ? invoicePreview(proposal.proposed) : null;
  const nonEurBlocked = !!preview?.invoice.currency && preview.invoice.currency.toUpperCase() !== "EUR";
  const valid =
    !nonEurBlocked &&
    ledger &&
    form.provider_contact_id &&
    form.number.trim() &&
    form.invoice_date &&
    form.net &&
    form.vat &&
    form.gross &&
    form.iban_confirm.trim() &&
    form.account;

  const submit = async () => {
    if (!proposal || !preview) return;
    setError(null);
    setStage("processing");
    const body = {
      invoice: {
        ledger_id: ledger,
        provider_contact_id: form.provider_contact_id,
        number: form.number.trim(),
        invoice_date: form.invoice_date,
        due_date: form.due_date || null,
        net: form.net,
        vat: form.vat,
        gross: form.gross,
        discount_percent: form.discount_percent || null,
        discount_until: form.discount_until || null,
        payee_iban: form.iban_confirm.trim(),
        document_id: preview.document_ids[0] ?? null,
        order_reference: form.order_reference.trim() || null,
        currency: preview.invoice.currency || "EUR",
        lines: [{ account_id: form.account, net: form.net, vat_percent: "19", vat: form.vat }],
      },
    };
    const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message);
      setStage("review");
      return;
    }
    const invoiceId = res.data.items?.[0]?.entity_id;
    if (invoiceId) router.push(`/rechnungen/${invoiceId}`);
    setStage("done");
  };

  if (stage === "idle" && !initialProposalId) {
    return (
      <button type="button" className={ui.button} onClick={() => setStage("picking")}>
        {t("extract.button")}
      </button>
    );
  }

  if (stage === "picking") {
    return (
      <div className={`${ui.card} flex flex-col gap-2`}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("extract.chooseFile")}</span>
          <input
            type="file"
            accept="application/pdf"
            className={ui.input}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void onFile(file);
            }}
          />
        </label>
        <button type="button" className={ui.button} onClick={() => setStage("idle")}>
          {t("extract.cancel")}
        </button>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }

  if (stage === "uploading" || stage === "queued" || (stage === "processing" && !proposal)) {
    return (
      <div className={`${ui.card} flex flex-col gap-2`} role="status" aria-live="polite">
        <p className="text-sm text-muted">{t(`extract.progress.${stage === "uploading" ? "uploading" : stage === "queued" ? "queued" : "processing"}`)}</p>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }

  if ((stage === "review" || stage === "processing") && proposal && preview) {
    return (
      <div className={`${ui.card} flex flex-col gap-3`} data-testid="invoice-review-form">
        <h3 className={ui.h2}>{t("extract.reviewTitle")}</h3>
        <p className={ui.notice}>{t("extract.reviewNotice")}</p>
        {preview.invoice.confidence != null ? (
          <p className="text-xs text-muted">{t("extract.confidence", { value: Math.round(preview.invoice.confidence * 100) })}</p>
        ) : null}
        {preview.invoice.property_number_guess ? (
          <p className="text-xs text-muted">{t("extract.propertyGuess", { value: preview.invoice.property_number_guess })}</p>
        ) : null}
        {(preview.warnings.length > 0 || preview.invoice.warnings.length > 0) ? (
          <div className="flex flex-col gap-1 rounded-md border border-warning-fg/20 bg-warning-bg p-2 text-sm text-warning-fg">
            <span className="font-medium">{t("extract.warnings")}</span>
            <ul className="list-disc pl-5">
              {[...preview.invoice.warnings, ...preview.warnings].map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {nonEurBlocked ? (
          <p role="alert" className={ui.alert}>
            {t("extract.currencyBlocked", { currency: preview.invoice.currency ?? "" })}
          </p>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.ledger")}</span>
            <select className={ui.input} value={ledger} onChange={(e) => { setLedger(e.target.value); setForm((p) => ({ ...p, account: "" })); }}>
              {ledgers.map((l) => (
                <option key={l.id} value={l.id}>{l.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.provider_search")}</span>
            <span className="flex gap-1">
              <input className={ui.input} value={q} onChange={(e) => setQ(e.target.value)} defaultValue={preview.invoice.supplier_name ?? ""} />
              <button type="button" className={ui.button} onClick={search} disabled={q.trim().length < 2}>{t("search")}</button>
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.provider")}</span>
            <select className={ui.input} value={form.provider_contact_id} onChange={set("provider_contact_id")}>
              <option value="">{t("choose")}</option>
              {preview.supplier_candidates.map((c) => (
                <option key={c.contact_id} value={c.contact_id}>{c.name}</option>
              ))}
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.number")}</span>
            <input className={ui.input} value={form.number} onChange={set("number")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.invoice_date")}</span>
            <input type="date" className={ui.input} value={form.invoice_date} onChange={set("invoice_date")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.net")}</span>
            <input className={ui.input} value={form.net} onChange={set("net")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>Steuer</span>
            <input className={ui.input} value={form.vat} onChange={set("vat")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("grossLabel")}</span>
            <input className={ui.input} value={form.gross} onChange={set("gross")} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("extract.ibanMasked")}</span>
            <input className={ui.input} value={preview.invoice.iban ?? ""} disabled readOnly />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("extract.ibanConfirm")}</span>
            <input className={ui.input} value={form.iban_confirm} onChange={set("iban_confirm")} />
            <span className={ui.help}>{t("extract.ibanConfirmHint")}</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.account")}</span>
            <select className={ui.input} value={form.account} onChange={set("account")}>
              <option value="">{t("choose")}</option>
              {(accounts[ledger] ?? []).map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("fields.order_reference")}</span>
            <input className={ui.input} value={form.order_reference} onChange={set("order_reference")} />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.primary} disabled={!valid || stage === "processing"} onClick={() => void submit()}>
            {t("extract.createDraft")}
          </button>
          <button
            type="button"
            className={ui.button}
            onClick={() => {
              setStage("idle");
              setProposal(null);
              onClose?.();
            }}
          >
            {t("extract.cancel")}
          </button>
        </div>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }

  return null;
}
