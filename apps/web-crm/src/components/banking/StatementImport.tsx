"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { bankAccountLabel, type BankAccountOption } from "./bankTypes";

type Run = { id: string; status: string; counts: Record<string, number>; errors: string[] };
type CsvPreview = {
  format_id: string;
  label: string;
  confidence: string;
  encoding: string;
  delimiter: string;
  headers: string[];
  row_count: number;
  sample_rows: Record<string, string>[];
  errors: { line: number; message: string }[];
  ready_to_import: boolean;
};
type SavedMapping = { id: string; property_bank_account_id: string; label: string; mapping: Record<string, unknown> };

/** Fields of `CsvColumnMappingIn` (banking/routers.py); `booking_date` is required, amount is
 *  either one column or debit and credit columns. */
export const MAPPING_FIELDS = [
  "booking_date",
  "amount",
  "amount_debit",
  "amount_credit",
  "value_date",
  "counterpart_name",
  "counterpart_iban",
  "counterpart_bic",
  "purpose",
  "end_to_end_id",
  "mandate_reference",
  "creditor_id",
  "own_iban",
  "bank_reference",
  "currency",
] as const;
type MappingField = (typeof MAPPING_FIELDS)[number];
type Mapping = Partial<Record<MappingField, string>>;

const MT940_SUFFIXES = [".sta", ".mt940", ".940", ".swi"];
export const ACCEPT = ".xml,.sta,.mt940,.940,.swi,.csv,application/xml,text/xml,text/csv";

export function fileKind(name: string): "camt" | "mt940" | "csv" {
  const lower = name.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (MT940_SUFFIXES.some((s) => lower.endsWith(s))) return "mt940";
  return "camt";
}

/** The document store checks the declared type against its allowlist; browsers send no or an
 *  opaque type for MT940 and sometimes for CSV, so the file is re-wrapped with the text type the
 *  API accepts (`text/plain`, `text/csv`). The file name is kept for format detection. */
export function uploadBlob(file: File, kind: "camt" | "mt940" | "csv"): Blob {
  if (kind === "mt940") return new Blob([file], { type: "text/plain" });
  if (kind === "csv") return new Blob([file], { type: "text/csv" });
  return file;
}

function apiMapping(mapping: Mapping): Record<string, string> {
  const out: Record<string, string> = {};
  for (const field of MAPPING_FIELDS) {
    const value = mapping[field];
    if (value) out[field] = value;
  }
  return out;
}

/** Statement upload (M11): CAMT.053 and MT940 go through `POST /banking/imports`; a bank CSV
 *  is previewed first (`POST /banking/imports/csv/preview`), gets a column mapping when the
 *  format is unknown, optionally saves that mapping per account and imports through
 *  `POST /banking/imports/csv`. Duplicates by bank reference are skipped by the API, unclear
 *  ones go to review (D05). */
export function StatementImport() {
  const t = useTranslations("Bank");
  const tc = useTranslations("Bank.csv");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [accounts, setAccounts] = useState<BankAccountOption[]>([]);
  const [accountId, setAccountId] = useState("");
  const [mapping, setMapping] = useState<Mapping>({});
  const [useMapping, setUseMapping] = useState(false);
  const [saved, setSaved] = useState<SavedMapping[]>([]);
  const [savedId, setSavedId] = useState("");
  const [mappingLabel, setMappingLabel] = useState("");
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const kind = file ? fileKind(file.name) : "camt";

  useEffect(() => {
    if (kind !== "csv" || accounts.length > 0) return;
    (async () => {
      const res = await bff<BankAccountOption[]>("/api/bff/banking/accounts");
      if (res.ok) setAccounts(res.data);
    })();
  }, [kind, accounts.length]);

  useEffect(() => {
    if (!accountId) {
      setSaved([]);
      return;
    }
    (async () => {
      const res = await bff<SavedMapping[]>(`/api/bff/banking/csv-mappings?property_bank_account_id=${accountId}`);
      if (res.ok) setSaved(res.data);
    })();
  }, [accountId]);

  const upload = async (): Promise<string | null> => {
    if (!file) return null;
    const form = new FormData();
    form.append("file", uploadBlob(file, kind), file.name);
    const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
    if (!doc.ok) {
      setError(doc.message);
      return null;
    }
    return doc.data.id;
  };

  const importStatement = async (docId: string) => {
    const res = await bff<Run>("/api/bff/banking/imports", {
      method: "POST",
      body: JSON.stringify({ document_id: docId }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRun(res.data);
    router.refresh();
  };

  const loadPreview = async (docId: string, withMapping: boolean) => {
    const body: Record<string, unknown> = { document_id: docId };
    if (withMapping && mapping.booking_date) body.mapping = apiMapping(mapping);
    const res = await bff<CsvPreview>("/api/bff/banking/imports/csv/preview", { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setPreview(res.data);
    if (!res.data.ready_to_import && !withMapping) setUseMapping(true);
  };

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setRun(null);
    const docId = documentId ?? (await upload());
    if (!docId) {
      setBusy(false);
      return;
    }
    setDocumentId(docId);
    if (kind === "csv") await loadPreview(docId, useMapping);
    else await importStatement(docId);
    setBusy(false);
  };

  const importCsv = async () => {
    if (!documentId) return;
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { document_id: documentId };
    if (accountId) body.property_bank_account_id = accountId;
    if (savedId) body.mapping_id = savedId;
    else if (useMapping && mapping.booking_date) body.mapping = apiMapping(mapping);
    const res = await bff<Run>("/api/bff/banking/imports/csv", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setRun(res.data);
    setPreview(null);
    setDocumentId(null);
    setFile(null);
    router.refresh();
  };

  const saveMapping = async () => {
    if (!accountId || !mappingLabel.trim() || !mapping.booking_date) return;
    setBusy(true);
    const res = await bff<SavedMapping>("/api/bff/banking/csv-mappings", {
      method: "POST",
      body: JSON.stringify({ property_bank_account_id: accountId, label: mappingLabel.trim(), mapping: apiMapping(mapping) }),
    });
    setBusy(false);
    if (res.ok) {
      setSaved((prev) => [...prev, res.data]);
      setSavedId(res.data.id);
      setSavedNotice(tc("mappingSaved", { label: res.data.label }));
    } else setError(res.message);
  };

  const mappingValid = Boolean(mapping.booking_date) && (Boolean(mapping.amount) || (Boolean(mapping.amount_debit) && Boolean(mapping.amount_credit)));
  const canImportCsv = Boolean(preview) && !busy && (Boolean(savedId) || preview?.ready_to_import || (useMapping && mappingValid && preview?.errors.length === 0));

  return (
    <section className="flex flex-col gap-2" data-testid="statement-import">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("statementFile")}</span>
          <input
            type="file"
            accept={ACCEPT}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setDocumentId(null);
              setPreview(null);
              setRun(null);
              setError(null);
            }}
          />
        </label>
        <button type="button" className={ui.primary} onClick={submit} disabled={busy || !file}>
          {kind === "csv" ? tc("preview") : t("import")}
        </button>
      </div>
      <p className={ui.help}>{t("statementFormats")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {preview ? (
        <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm" data-testid="csv-preview">
          <p>
            {tc("detected", { label: preview.label, confidence: preview.confidence })} · {tc("rows", { count: preview.row_count })} ·{" "}
            {tc("encoding", { encoding: preview.encoding, delimiter: preview.delimiter })}
          </p>
          {preview.errors.length > 0 ? (
            <ul className={`${ui.warning} list-disc pl-5`} data-testid="csv-errors">
              {preview.errors.slice(0, 10).map((e) => (
                <li key={`${e.line}-${e.message}`}>{tc("rowError", { line: e.line, message: e.message })}</li>
              ))}
            </ul>
          ) : null}
          <div className="overflow-x-auto">
            <table className="mhvp-table text-xs">
              <thead>
                <tr>
                  {preview.headers.map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.slice(0, 5).map((row, i) => (
                  <tr key={i}>
                    {preview.headers.map((h) => (
                      <td key={h}>{row[h] ?? ""}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{tc("account")}</span>
            <select
              className={ui.input}
              value={accountId}
              onChange={(e) => {
                setAccountId(e.target.value);
                setSavedId("");
              }}
            >
              <option value="">{tc("noAccount")}</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {bankAccountLabel(a)}
                </option>
              ))}
            </select>
          </label>
          {saved.length > 0 ? (
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{tc("savedMapping")}</span>
              <select className={ui.input} value={savedId} onChange={(e) => setSavedId(e.target.value)}>
                <option value="">{tc("noSavedMapping")}</option>
                {saved.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useMapping} onChange={(e) => setUseMapping(e.target.checked)} />
            {tc("useMapping")}
          </label>
          {useMapping ? (
            <div className="grid gap-2 sm:grid-cols-2" data-testid="csv-mapping">
              {MAPPING_FIELDS.map((field) => (
                <label key={field} className="flex flex-col gap-1">
                  <span className={ui.label}>{tc(`field.${field}`)}</span>
                  <select className={ui.input} value={mapping[field] ?? ""} onChange={(e) => setMapping((prev) => ({ ...prev, [field]: e.target.value || undefined }))}>
                    <option value="">{tc("noColumn")}</option>
                    {preview.headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
              <p className={`${ui.help} sm:col-span-2`}>{tc("mappingRule")}</p>
              <div className="flex flex-wrap items-end gap-2 sm:col-span-2">
                <button type="button" className={ui.button} onClick={() => documentId && loadPreview(documentId, true)} disabled={busy || !mappingValid}>
                  {tc("refreshPreview")}
                </button>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{tc("mappingLabel")}</span>
                  <input className={ui.input} value={mappingLabel} onChange={(e) => setMappingLabel(e.target.value)} maxLength={120} />
                </label>
                <button type="button" className={ui.button} onClick={saveMapping} disabled={busy || !accountId || !mappingValid || !mappingLabel.trim()}>
                  {tc("saveMapping")}
                </button>
              </div>
            </div>
          ) : null}
          {savedNotice ? <p className={ui.success}>{savedNotice}</p> : null}
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} onClick={importCsv} disabled={!canImportCsv}>
              {tc("import")}
            </button>
          </div>
        </div>
      ) : null}
      {run ? (
        <p className="text-sm" data-testid="import-result">
          {Object.entries(run.counts)
            .map(([k, v]) => `${t.has(`counts.${k}`) ? t(`counts.${k}`) : k}: ${v}`)
            .join(" · ")}
        </p>
      ) : null}
    </section>
  );
}
