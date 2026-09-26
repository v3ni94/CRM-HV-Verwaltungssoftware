"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { formatConfidence, formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type DraftField = { value: string | null; confidence: number; source: "ai" | "xml" | "ai_estimate" | "local" | "none"; note: string | null };
/** D42: one contradiction between the structured XML part and the PDF text or the AI reading. */
export type DraftConflict = { field: string; xml: string | null; other: string | null; other_source: "pdf_text" | "ai"; note: string };
export type XmlLine = { position: string | null; description: string | null; quantity: string | null; unit: string | null; net: string | null; vat_percent: string | null };
export type ReceiptDraft = {
  id: string;
  document_id: string;
  source: "upload" | "mail_attachment" | "paperless";
  status: "extracting" | "proposed" | "failed" | "confirmed" | "rejected";
  fields: Record<string, DraftField>;
  iban_candidates: { masked: string; checksum_ok: boolean; source: "local" }[];
  supplier_candidates: { contact_id: string; name: string; score: number; reasons: string[] }[];
  property_suggestions: { property_id: string; number: string; name: string; score: number; reason: string }[];
  warnings: string[];
  questions: string[];
  masked_excerpt: string | null;
  e_invoice_format?: "none" | "xrechnung" | "zugferd";
  xml_lines?: XmlLine[];
  xml_payment?: { means_code: string | null; payee_name: string | null; reference: string | null; terms: string | null; iban_masked: string | null; iban_checksum_ok: boolean | null } | null;
  conflicts?: DraftConflict[];
  findings?: string[];
  error: string | null;
  invoice_id: string | null;
  created_at: string;
};

type Option = { id: string; label: string };
const FIELD_ORDER = [
  "supplier_name",
  "invoice_number",
  "invoice_date",
  "due_date",
  "net",
  "vat",
  "gross",
  "currency",
  "discount_percent",
  "discount_until",
  "order_reference",
  "recipient_name",
  "section_35a_amount",
  "property_ref",
] as const;
type FieldName = (typeof FIELD_ORDER)[number];
/** Shown for review only; the confirmation never sends them (the apply schema has no such
 *  field, a § 35a estimate is never taken over, D44). */
const READ_ONLY_FIELDS: ReadonlySet<FieldName> = new Set<FieldName>(["recipient_name", "section_35a_amount"]);
type Form = Record<FieldName, string>;
const POLL_MS = 2500;
const R = "/api/bff/receipts/drafts";

function formFromDraft(draft: ReceiptDraft): Form {
  const form = {} as Form;
  for (const name of FIELD_ORDER) form[name] = draft.fields[name]?.value ?? "";
  return form;
}

/** Lowest field confidence of a draft (the weakest value decides how much review it needs);
 *  null while nothing has been extracted yet. */
export function minConfidence(draft: ReceiptDraft): number | null {
  const values = Object.values(draft.fields).map((f) => f.confidence);
  return values.length === 0 ? null : Math.min(...values);
}

function propertyLabel(draft: ReceiptDraft): string {
  const ref = draft.fields.property_ref?.value ?? null;
  const match = draft.property_suggestions.find((p) => p.property_id === ref) ?? draft.property_suggestions[0];
  return match ? `${match.number} ${match.name}` : (ref ?? "");
}

function confidenceClass(value: number): string {
  if (value >= 0.85) return ui.badgeSuccess;
  if (value >= 0.6) return ui.badgeWarning;
  return ui.badgeDanger;
}

/** Belegeingang: Entwurfsliste, Erfassung (Upload, Paperless) und Feldprüfung. Jeder Wert ist ein
 *  Vorschlag; die IBAN wird nie aus dem Vorschlag übernommen (rule 0.1.6). Die Bestätigung legt
 *  einen offenen Rechnungsentwurf an, keine Buchung. */
export function ReceiptIntake({
  initialDrafts,
  initialDraftId,
  ledgers,
  accounts,
}: {
  initialDrafts: ReceiptDraft[];
  initialDraftId: string | null;
  ledgers: Option[];
  accounts: Record<string, Option[]>;
}) {
  const t = useTranslations("Receipts");
  const [drafts, setDrafts] = useState<ReceiptDraft[]>(initialDrafts);
  const [filter, setFilter] = useState<"open" | "all">("open");
  const [selectedId, setSelectedId] = useState<string | null>(initialDraftId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paperlessId, setPaperlessId] = useState("");
  const [form, setForm] = useState<Form | null>(null);
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [account, setAccount] = useState("");
  const [provider, setProvider] = useState("");
  const [providerQuery, setProviderQuery] = useState("");
  const [providers, setProviders] = useState<Option[]>([]);
  const [iban, setIban] = useState("");
  const [ibanConfirmed, setIbanConfirmed] = useState(false);
  const [conflictsAcknowledged, setConflictsAcknowledged] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const selected = useMemo(() => drafts.find((d) => d.id === selectedId) ?? null, [drafts, selectedId]);

  const reload = useCallback(async () => {
    const res = await bff<{ items: ReceiptDraft[] }>(`${R}?limit=200`);
    if (res.ok) setDrafts(res.data.items);
  }, []);

  useEffect(() => {
    if (!drafts.some((d) => d.status === "extracting")) return;
    const handle = setTimeout(() => void reload(), POLL_MS);
    return () => clearTimeout(handle);
  }, [drafts, reload]);

  useEffect(() => {
    if (!selected) {
      setForm(null);
      return;
    }
    setForm(formFromDraft(selected));
    setProvider(selected.supplier_candidates[0]?.contact_id ?? "");
    setIban("");
    setIbanConfirmed(false);
    setConflictsAcknowledged(false);
    setAccount("");
    // Only the selected draft's identity and status matter; the form is the reviewer's copy.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.status]);

  const visible = drafts
    .filter((d) => filter === "all" || ["extracting", "proposed", "failed"].includes(d.status))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  const startFromFile = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      body.set("title", file.name);
      const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body });
      if (!doc.ok) throw new Error(doc.message);
      const res = await bff<ReceiptDraft>(R, { method: "POST", body: JSON.stringify({ document_id: doc.data.id, source: "upload" }) });
      if (!res.ok) throw new Error(res.message);
      setDrafts((p) => [res.data, ...p]);
      setSelectedId(res.data.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const startFromPaperless = async () => {
    const id = Number(paperlessId);
    if (!Number.isInteger(id) || id < 1) return;
    setBusy(true);
    setError(null);
    const res = await bff<ReceiptDraft>(`${R}/paperless`, { method: "POST", body: JSON.stringify({ paperless_document_id: id }) });
    if (!res.ok) setError(res.message);
    else {
      setDrafts((p) => [res.data, ...p]);
      setSelectedId(res.data.id);
      setPaperlessId("");
    }
    setBusy(false);
  };

  const searchProviders = async () => {
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(providerQuery.trim())}`);
    if (res.ok) setProviders(res.data.items.map((c) => ({ id: c.id, label: c.display_name })));
  };

  const setField = (name: FieldName) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((p) => (p ? { ...p, [name]: e.target.value } : p));

  const canConfirm =
    !!selected &&
    selected.status === "proposed" &&
    !!form &&
    !!ledger &&
    !!account &&
    !!provider &&
    form.invoice_number.trim() !== "" &&
    form.invoice_date !== "" &&
    form.net !== "" &&
    form.vat !== "" &&
    form.gross !== "" &&
    (iban.trim() === "" || ibanConfirmed) &&
    ((selected.conflicts ?? []).length === 0 || conflictsAcknowledged);

  const confirm = async () => {
    if (!selected || !form || !canConfirm) return;
    setBusy(true);
    setError(null);
    const body = {
      iban_confirmed: ibanConfirmed && iban.trim() !== "",
      conflicts_acknowledged: (selected.conflicts ?? []).length > 0 && conflictsAcknowledged,
      invoice: {
        ledger_id: ledger,
        provider_contact_id: provider,
        number: form.invoice_number.trim(),
        invoice_date: form.invoice_date,
        due_date: form.due_date || null,
        net: form.net,
        vat: form.vat,
        gross: form.gross,
        discount_percent: form.discount_percent || null,
        discount_until: form.discount_until || null,
        payee_iban: iban.trim() || null,
        document_id: selected.document_id,
        order_reference: form.order_reference.trim() || null,
        currency: form.currency || "EUR",
        lines: [{ account_id: account, net: form.net, vat_percent: "19", vat: form.vat }],
      },
    };
    const res = await bff<ReceiptDraft>(`${R}/${selected.id}/confirm`, { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) setError(res.message);
    else setDrafts((p) => p.map((d) => (d.id === res.data.id ? res.data : d)));
    setBusy(false);
  };

  const reject = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    const res = await bff<ReceiptDraft>(`${R}/${selected.id}/reject`, { method: "POST", body: JSON.stringify({ reason: rejectReason || null }) });
    if (!res.ok) setError(res.message);
    else {
      setDrafts((p) => p.map((d) => (d.id === res.data.id ? res.data : d)));
      setRejectReason("");
    }
    setBusy(false);
  };

  return (
    <div className={ui.sectionGap}>
      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("intake.title")}</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("intake.upload")}</span>
            <input
              type="file"
              accept="application/pdf,application/xml,text/xml,.xml"
              className={ui.input}
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void startFromFile(file);
                e.target.value = "";
              }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("intake.paperlessId")}</span>
            <span className="flex gap-1">
              <input className={ui.input} inputMode="numeric" value={paperlessId} onChange={(e) => setPaperlessId(e.target.value)} />
              <button type="button" className={ui.button} disabled={busy || !paperlessId} onClick={() => void startFromPaperless()}>
                {t("intake.paperlessStart")}
              </button>
            </span>
          </label>
        </div>
        {busy ? <p className="text-sm text-muted" role="status">{t("intake.uploading")}</p> : null}
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </section>

      <section className={`${ui.card} flex flex-col gap-3`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className={ui.h2}>{t("list.title")}</h2>
          <div className="flex gap-1">
            <button type="button" className={filter === "open" ? ui.primary : ui.button} onClick={() => setFilter("open")}>
              {t("list.filterOpen")}
            </button>
            <button type="button" className={filter === "all" ? ui.primary : ui.button} onClick={() => setFilter("all")}>
              {t("list.filterAll")}
            </button>
          </div>
        </div>
        {visible.length === 0 ? (
          <p className="text-sm text-muted">{t("list.empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("list.columns.created")}</th>
                  <th>{t("list.columns.supplier")}</th>
                  <th className="num">{t("list.columns.amount")}</th>
                  <th>{t("list.columns.date")}</th>
                  <th>{t("list.columns.property")}</th>
                  <th title={t("list.confidenceHint")}>{t("list.columns.confidence")}</th>
                  <th>{t("list.columns.source")}</th>
                  <th>{t("list.columns.status")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((d) => {
                  const confidence = minConfidence(d);
                  return (
                    <tr key={d.id} className={d.id === selectedId ? "bg-surface" : undefined}>
                      <td>{formatDateTime(d.created_at)}</td>
                      <td>{d.fields.supplier_name?.value ?? ""}</td>
                      <td className="num">{d.fields.gross?.value ? formatEur(d.fields.gross.value) : ""}</td>
                      <td>{d.fields.invoice_date?.value ? formatDate(d.fields.invoice_date.value) : ""}</td>
                      <td>{propertyLabel(d)}</td>
                      <td>{confidence === null ? "" : <span className={confidenceClass(confidence)}>{formatConfidence(confidence) || "0 %"}</span>}</td>
                      <td>{t(`source.${d.source}`)}</td>
                      <td>
                        <span className={ui.badge}>{t(`status.${d.status}`)}</span>
                      </td>
                      <td>
                        <button type="button" className={ui.buttonSm} onClick={() => setSelectedId(d.id)}>
                          {t("list.open")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && form ? (
        <section className={`${ui.card} flex flex-col gap-3`} data-testid="receipt-review">
          <h2 className={ui.h2}>{t("review.title")}</h2>
          {selected.status === "extracting" ? <p className="text-sm text-muted" role="status">{t("review.extracting")}</p> : null}
          {selected.status === "failed" ? <p role="alert" className={ui.alert}>{t("review.failed", { reason: selected.error ?? "" })}</p> : null}
          {selected.status === "confirmed" ? (
            <p className={ui.success}>
              {t("review.confirmed")}{" "}
              {selected.invoice_id ? (
                <Link href={`/rechnungen/${selected.invoice_id}`} className="font-medium underline">
                  {t("review.openInvoice")}
                </Link>
              ) : null}
            </p>
          ) : null}
          {selected.status === "rejected" ? <p className="text-sm text-muted">{t("review.decided")}</p> : null}
          {selected.status === "proposed" ? <p className={ui.notice}>{t("review.hint")}</p> : null}
          {selected.e_invoice_format && selected.e_invoice_format !== "none" ? (
            <p className="text-sm">
              <span className={ui.badge}>{t(`review.einvoice.${selected.e_invoice_format}`)}</span> {t("review.einvoiceHint")}
            </p>
          ) : null}

          {(selected.conflicts ?? []).length > 0 ? (
            <div role="alert" className="flex flex-col gap-1 rounded-md border border-danger-fg/30 bg-danger-bg p-2 text-sm text-danger-fg" data-testid="receipt-conflicts">
              <span className="font-medium">{t("review.conflicts")}</span>
              <ul className="list-disc pl-5">
                {(selected.conflicts ?? []).map((c, i) => (
                  <li key={i}>
                    {t("review.conflictLine", {
                      field: FIELD_ORDER.includes(c.field as FieldName) ? t(`review.fields.${c.field}`) : c.field,
                      xml: c.xml ?? t("review.conflictMissing"),
                      source: t(`review.conflictSource.${c.other_source}`),
                      other: c.other ?? t("review.conflictMissing"),
                    })}{" "}
                    <span className="text-xs">{c.note}</span>
                  </li>
                ))}
              </ul>
              {selected.status === "proposed" ? (
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={conflictsAcknowledged} onChange={(e) => setConflictsAcknowledged(e.target.checked)} />
                  {t("review.conflictsAcknowledge")}
                </label>
              ) : null}
            </div>
          ) : null}
          {(selected.findings ?? []).length > 0 ? (
            <div className="flex flex-col gap-1 rounded-md border border-warning-fg/20 bg-warning-bg p-2 text-sm text-warning-fg" data-testid="receipt-findings">
              <span className="font-medium">{t("review.findings")}</span>
              <ul className="list-disc pl-5">
                {(selected.findings ?? []).map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {selected.warnings.length > 0 ? (
            <div className="flex flex-col gap-1 rounded-md border border-warning-fg/20 bg-warning-bg p-2 text-sm text-warning-fg">
              <span className="font-medium">{t("review.warnings")}</span>
              <ul className="list-disc pl-5">
                {selected.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {selected.questions.length > 0 ? (
            <div className="flex flex-col gap-1 text-sm text-muted">
              <span className="font-medium">{t("review.questions")}</span>
              <ul className="list-disc pl-5">
                {selected.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {selected.status !== "extracting" ? (
            <div className="overflow-x-auto">
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("review.columns.field")}</th>
                    <th>{t("review.columns.proposed")}</th>
                    <th>{t("review.columns.confidence")}</th>
                    <th>{t("review.columns.source")}</th>
                    <th>{t("review.columns.note")}</th>
                    <th>{t("review.columns.value")}</th>
                  </tr>
                </thead>
                <tbody>
                  {FIELD_ORDER.map((name) => {
                    const f = selected.fields[name] ?? { value: null, confidence: 0, source: "none", note: null };
                    const editable = selected.status === "proposed" && !READ_ONLY_FIELDS.has(name);
                    const isDate = name.endsWith("_date") || name === "discount_until";
                    const conflicting = (selected.conflicts ?? []).some((c) => c.field === name);
                    if (f.source === "none" && READ_ONLY_FIELDS.has(name)) return null;
                    return (
                      <tr key={name} className={conflicting ? "bg-danger-bg" : undefined} data-conflict={conflicting ? "true" : undefined}>
                        <td className="font-medium">{t(`review.fields.${name}`)}</td>
                        <td>{name === "property_ref" ? (selected.property_suggestions.find((p) => p.property_id === f.value)?.name ?? f.value ?? "") : (f.value ?? "")}</td>
                        <td>
                          <span className={confidenceClass(f.confidence)}>{formatConfidence(f.confidence) || "0 %"}</span>
                        </td>
                        <td>
                          <span className={f.source === "xml" ? ui.badgeSuccess : f.source === "ai_estimate" ? ui.badgeDanger : undefined}>{t(`review.sourceLabel.${f.source}`)}</span>
                        </td>
                        <td className="text-xs text-muted">{f.note ?? ""}</td>
                        <td>
                          {READ_ONLY_FIELDS.has(name) ? (
                            <span className="text-sm text-muted">{t("review.readOnly")}</span>
                          ) : name === "property_ref" ? (
                            <select className={ui.input} value={form[name]} onChange={setField(name)} disabled={!editable}>
                              <option value="">{t("review.choose")}</option>
                              {selected.property_suggestions.map((p) => (
                                <option key={p.property_id} value={p.property_id}>
                                  {p.number} {p.name}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <input type={isDate ? "date" : "text"} className={ui.input} value={form[name]} onChange={setField(name)} disabled={!editable} />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}

          {selected.property_suggestions.length > 0 ? (
            <p className="text-xs text-muted">
              {t("review.propertySuggestions")}:{" "}
              {selected.property_suggestions.map((p) => t("review.propertyReason", { reason: `${p.number} ${p.name}, ${p.reason}`, score: Math.round(p.score * 100) })).join("; ")}
            </p>
          ) : null}

          {selected.status === "proposed" ? (
            <>
              <div className="grid gap-2 sm:grid-cols-4">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.ledger")}</span>
                  <select
                    className={ui.input}
                    value={ledger}
                    onChange={(e) => {
                      setLedger(e.target.value);
                      setAccount("");
                    }}
                  >
                    {ledgers.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.account")}</span>
                  <select className={ui.input} value={account} onChange={(e) => setAccount(e.target.value)}>
                    <option value="">{t("review.choose")}</option>
                    {(accounts[ledger] ?? []).map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.providerSearch")}</span>
                  <span className="flex gap-1">
                    <input className={ui.input} value={providerQuery} onChange={(e) => setProviderQuery(e.target.value)} />
                    <button type="button" className={ui.button} onClick={() => void searchProviders()} disabled={providerQuery.trim().length < 2}>
                      {t("review.search")}
                    </button>
                  </span>
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.provider")}</span>
                  <select className={ui.input} value={provider} onChange={(e) => setProvider(e.target.value)}>
                    <option value="">{t("review.choose")}</option>
                    {selected.supplier_candidates.map((c) => (
                      <option key={c.contact_id} value={c.contact_id}>
                        {c.name}
                      </option>
                    ))}
                    {providers
                      .filter((p) => !selected.supplier_candidates.some((c) => c.contact_id === p.id))
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.label}
                        </option>
                      ))}
                  </select>
                </label>
              </div>

              <div className="flex flex-col gap-2 rounded-md border border-border p-3">
                <span className={ui.label}>{t("review.ibanCandidates")}</span>
                {selected.iban_candidates.length === 0 ? (
                  <span className="text-sm text-muted">{t("review.ibanNone")}</span>
                ) : (
                  <ul className="flex flex-wrap gap-2 text-sm">
                    {selected.iban_candidates.map((c, i) => (
                      <li key={i} className={c.checksum_ok ? ui.badge : ui.badgeDanger}>
                        {c.masked}
                        {c.checksum_ok ? "" : ` (${t("review.ibanChecksumBad")})`}
                      </li>
                    ))}
                  </ul>
                )}
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.ibanInput")}</span>
                  <input className={ui.input} value={iban} onChange={(e) => setIban(e.target.value)} autoComplete="off" />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={ibanConfirmed} onChange={(e) => setIbanConfirmed(e.target.checked)} disabled={iban.trim() === ""} />
                  {t("review.ibanConfirm")}
                </label>
                <span className={ui.help}>{t("review.ibanHint")}</span>
              </div>

              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <label className="flex flex-col gap-1 sm:w-1/2">
                  <span className={ui.label}>{t("review.rejectReason")}</span>
                  <input className={ui.input} value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                </label>
                <div className={ui.formActions}>
                  <button type="button" className={ui.danger} disabled={busy} onClick={() => void reject()}>
                    {t("review.reject")}
                  </button>
                  <button type="button" className={ui.primary} disabled={busy || !canConfirm} onClick={() => void confirm()}>
                    {t("review.confirm")}
                  </button>
                </div>
              </div>
            </>
          ) : null}

          {(selected.xml_lines ?? []).length > 0 ? (
            <details className="text-xs text-muted" data-testid="receipt-xml-lines">
              <summary className="cursor-pointer">{t("review.xmlLines", { count: (selected.xml_lines ?? []).length })}</summary>
              <table className={`${ui.table} mt-2`}>
                <thead>
                  <tr>
                    <th>{t("review.xmlLineColumns.position")}</th>
                    <th>{t("review.xmlLineColumns.description")}</th>
                    <th className="num">{t("review.xmlLineColumns.quantity")}</th>
                    <th className="num">{t("review.xmlLineColumns.net")}</th>
                    <th className="num">{t("review.xmlLineColumns.vat")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(selected.xml_lines ?? []).map((ln, i) => (
                    <tr key={i}>
                      <td>{ln.position ?? ""}</td>
                      <td>{ln.description ?? ""}</td>
                      <td className="num">{[ln.quantity, ln.unit].filter(Boolean).join(" ")}</td>
                      <td className="num">{ln.net ? formatEur(ln.net) : ""}</td>
                      <td className="num">{ln.vat_percent ? `${ln.vat_percent} %` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ) : null}
          {selected.xml_payment ? (
            <p className="text-xs text-muted" data-testid="receipt-xml-payment">
              {t("review.xmlPayment")}: {[selected.xml_payment.payee_name, selected.xml_payment.iban_masked, selected.xml_payment.reference, selected.xml_payment.terms].filter(Boolean).join(", ") || t("review.xmlPaymentNone")}
            </p>
          ) : null}
          {selected.masked_excerpt ? (
            <details className="text-xs text-muted">
              <summary className="cursor-pointer">{t("review.maskedExcerpt")}</summary>
              <pre className="mt-2 whitespace-pre-wrap break-words rounded-md bg-surface p-2">{selected.masked_excerpt}</pre>
            </details>
          ) : null}
          <p className={ui.help}>{formatDate(selected.created_at)}</p>
        </section>
      ) : null}
    </div>
  );
}
