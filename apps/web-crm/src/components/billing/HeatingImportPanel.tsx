"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { HeatingImportRowsForm } from "@/components/aj17/HeatingImportRowsForm";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type PropertyRow = { id: string; number: string; name: string };
type UnitRow = { id: string; number: string };
type ContractRow = { id: string; number: string; unit_id: string };
type StatementRow = { id: string; property_id: string; period_from: string; period_to: string; status: string; version: number };
type Row = {
  user_number: string;
  heating_base: string;
  heating_consumption: string;
  hot_water_base: string;
  hot_water_consumption: string;
  co2_landlord: string;
  co2_tenant: string;
};
type Check = { grand_total?: string; findings: string[]; duplicates?: unknown[] };
type ImportRow = {
  id: string;
  property_id: string;
  statement_id: string | null;
  document_id: string | null;
  provider_name: string;
  period_from: string;
  period_to: string;
  document_total: string;
  user_mapping: Record<string, { unit_id: string; contract_id?: string | null }>;
  rows: Row[];
  csv_meta: { file_name?: string | null; row_count?: number } | null;
  status: "draft" | "checked" | "applied";
  check_result: Check | null;
  duplicate_ack_reason: string | null;
  applied_at: string | null;
};
type DocumentOut = { id: string; filename: string };

const CSV_FIELDS = ["user_number", "heating_base", "heating_consumption", "hot_water_base", "hot_water_consumption", "co2_landlord", "co2_tenant"] as const;

/** First line of a CSV as header names, split at the chosen delimiter (quotes are removed, no guessing). */
export function csvHeaders(content: string, delimiter: string): string[] {
  const first = content.replace(/^﻿/, "").split(/\r?\n/, 1)[0] ?? "";
  return first
    .split(delimiter)
    .map((h) => h.trim().replace(/^"(.*)"$/, "$1"))
    .filter((h) => h !== "");
}

/** Heizkostenimport des Messdiensts (M17-09) unter Abrechnung: Liste je Objekt, Anlage mit
 *  Originaldokument, CSV mit expliziter Spaltenzuordnung, Zuordnung der Nutzernummern, Prüfbefunde,
 *  Übernahme in eine Abrechnung im Entwurf. Lesen accounting:read, Ändern accounting:create. */
export function HeatingImportPanel({ permissions }: { permissions: string[] }) {
  const t = useTranslations("HeatingImport");
  const canRead = permissions.includes("accounting:read");
  const canWrite = permissions.includes("accounting:create");
  const [properties, setProperties] = useState<PropertyRow[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [imports, setImports] = useState<ImportRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [units, setUnits] = useState<UnitRow[]>([]);
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [statements, setStatements] = useState<StatementRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // create form
  const [provider, setProvider] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [total, setTotal] = useState("");
  const [file, setFile] = useState<File | null>(null);
  // csv form
  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("");
  const [delimiter, setDelimiter] = useState(";");
  const [decimalComma, setDecimalComma] = useState(true);
  const [columnMap, setColumnMap] = useState<Record<string, string>>({});
  // mapping, check, apply
  const [mapping, setMapping] = useState<Record<string, { unit_id: string; contract_id: string }>>({});
  const [ackReason, setAckReason] = useState("");
  const [statementId, setStatementId] = useState("");

  const selected = imports.find((i) => i.id === selectedId) ?? null;

  useEffect(() => {
    if (!canRead) return;
    void (async () => {
      // GET /properties answers a page ({items}); older answers were a plain list.
      const res = await bff<PropertyRow[] | { items: PropertyRow[] }>("/api/bff/properties?page_size=200");
      if (res.ok) setProperties(Array.isArray(res.data) ? res.data : (res.data.items ?? []));
      else setError(res.message);
    })();
  }, [canRead]);

  const loadImports = useCallback(async (pid: string) => {
    const res = await bff<ImportRow[]>(`/api/bff/billing/heating-cost-imports${pid ? `?property_id=${pid}` : ""}`);
    if (res.ok) {
      setImports(res.data);
      setError(null);
    } else setError(res.message);
  }, []);

  useEffect(() => {
    if (canRead) void loadImports(propertyId);
  }, [canRead, propertyId, loadImports]);

  // Reference data of the selected import's property (units, contracts, draft statements).
  const selectedProperty = selected?.property_id ?? null;
  useEffect(() => {
    if (!selectedProperty) return;
    void (async () => {
      const [u, c, s] = await Promise.all([
        bff<UnitRow[]>(`/api/bff/properties/${selectedProperty}/units`),
        bff<ContractRow[]>(`/api/bff/contracts?property_id=${selectedProperty}`),
        bff<StatementRow[]>("/api/bff/statements"),
      ]);
      if (u.ok) setUnits(u.data);
      if (c.ok) setContracts(c.data);
      if (s.ok) setStatements(s.data.filter((x) => x.property_id === selectedProperty && x.status === "draft"));
    })();
  }, [selectedProperty]);

  useEffect(() => {
    if (!selected) return;
    const next: Record<string, { unit_id: string; contract_id: string }> = {};
    for (const r of selected.rows) {
      const m = selected.user_mapping[r.user_number];
      next[r.user_number] = { unit_id: m?.unit_id ?? "", contract_id: m?.contract_id ?? "" };
    }
    setMapping(next);
    setAckReason(selected.duplicate_ack_reason ?? "");
  }, [selected]);

  function replace(row: ImportRow) {
    setImports((list) => (list.some((i) => i.id === row.id) ? list.map((i) => (i.id === row.id ? row : i)) : [row, ...list]));
  }

  async function call<T>(path: string, method: string, body: unknown): Promise<T | null> {
    setBusy(true);
    setNotice(null);
    const res = await bff<T>(`/api/bff/billing/heating-cost-imports${path}`, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    setError(null);
    return res.data;
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!propertyId) return;
    setBusy(true);
    let documentId: string | null = null;
    if (file) {
      const form = new FormData();
      form.set("file", file);
      form.set("title", `${t("documentTitle")} ${provider}`);
      const up = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body: form });
      if (!up.ok) {
        setBusy(false);
        setError(up.message);
        return;
      }
      documentId = up.data.id;
    }
    setBusy(false);
    const row = await call<ImportRow>("", "POST", {
      property_id: propertyId,
      document_id: documentId,
      provider_name: provider,
      period_from: from,
      period_to: to,
      document_total: total.replace(",", "."),
    });
    if (row) {
      replace(row);
      setSelectedId(row.id);
      setNotice(t("created"));
    }
  }

  async function readCsv(f: File | null) {
    if (!f) return;
    setCsvName(f.name);
    setCsvText(await f.text());
    setColumnMap({});
  }

  async function uploadCsv() {
    if (!selected) return;
    const row = await call<ImportRow>(`/${selected.id}/csv`, "POST", { content: csvText, delimiter, decimal_comma: decimalComma, column_map: columnMap, file_name: csvName || null });
    if (row) {
      replace(row);
      setNotice(t("csvDone", { count: row.rows.length }));
    }
  }

  async function saveMapping() {
    if (!selected) return;
    const body: Record<string, { unit_id: string; contract_id?: string }> = {};
    for (const [user, m] of Object.entries(mapping)) if (m.unit_id) body[user] = { unit_id: m.unit_id, ...(m.contract_id ? { contract_id: m.contract_id } : {}) };
    const row = await call<ImportRow>(`/${selected.id}/mapping`, "PUT", { mapping: body });
    if (row) {
      replace(row);
      setNotice(t("mappingSaved"));
    }
  }

  async function runCheck() {
    if (!selected) return;
    const row = await call<ImportRow>(`/${selected.id}/check`, "POST", { duplicate_ack_reason: ackReason.trim() || null });
    if (row) replace(row);
  }

  async function apply() {
    if (!selected || !statementId) return;
    const row = await call<ImportRow>(`/${selected.id}/apply`, "POST", { statement_id: statementId });
    if (row) {
      replace(row);
      setNotice(t("applied"));
    }
  }

  if (!canRead) return null;
  const headers = csvText ? csvHeaders(csvText, delimiter) : [];
  const csvComplete = CSV_FIELDS.every((f) => columnMap[f]);
  const findings = selected?.check_result?.findings ?? [];
  const hasDuplicates = (selected?.check_result?.duplicates?.length ?? 0) > 0;
  const editable = canWrite && selected?.status !== "applied";

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="heating-import-title">
      <h2 id="heating-import-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("description")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      <label className="flex max-w-md flex-col gap-1">
        <span className={ui.label}>{t("property")}</span>
        <select className={ui.input} value={propertyId} onChange={(e) => { setPropertyId(e.target.value); setSelectedId(null); }} data-testid="hci-property">
          <option value="">{t("allProperties")}</option>
          {properties.map((p) => (
            <option key={p.id} value={p.id}>
              {p.number} {p.name}
            </option>
          ))}
        </select>
      </label>

      {imports.length === 0 ? (
        <p className={ui.help}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table" data-testid="hci-list">
            <thead>
              <tr>
                <th>{t("provider")}</th>
                <th>{t("period")}</th>
                <th>{t("documentTotal")}</th>
                <th>{t("statusLabel")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {imports.map((i) => (
                <tr key={i.id}>
                  <td>{i.provider_name}</td>
                  <td>
                    {formatDate(i.period_from)} bis {formatDate(i.period_to)}
                  </td>
                  <td>{formatEur(i.document_total)}</td>
                  <td>{t(`status.${i.status}`)}</td>
                  <td>
                    <button type="button" className={ui.buttonSm} onClick={() => setSelectedId(i.id)}>
                      {t("open")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canWrite && propertyId ? (
        <form onSubmit={create} className="flex flex-col gap-2 border-t border-card-line pt-3" aria-label={t("createTitle")}>
          <h3 className={ui.h3}>{t("createTitle")}</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("provider")}</span>
              <input className={ui.input} value={provider} onChange={(e) => setProvider(e.target.value)} minLength={2} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("documentTotal")}</span>
              <input className={ui.input} inputMode="decimal" value={total} onChange={(e) => setTotal(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("periodFrom")}</span>
              <input className={ui.input} type="date" value={from} onChange={(e) => setFrom(e.target.value)} required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("periodTo")}</span>
              <input className={ui.input} type="date" value={to} onChange={(e) => setTo(e.target.value)} required />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("originalDocument")}</span>
            <input className={ui.input} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} data-testid="hci-document" />
          </label>
          <div>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("create")}
            </button>
          </div>
        </form>
      ) : null}

      {selected ? (
        <div className="flex flex-col gap-3 border-t border-card-line pt-3" data-testid="hci-detail">
          <h3 className={ui.h3}>
            {selected.provider_name}, {formatDate(selected.period_from)} bis {formatDate(selected.period_to)}
          </h3>
          <p className={ui.help}>
            {t(`status.${selected.status}`)} · {selected.document_id ? t("documentLinked") : t("documentMissing")} · {t("rowCount", { count: selected.rows.length })}
          </p>
          {selected.status === "applied" ? <p className={ui.notice}>{t("lockedApplied")}</p> : null}

          {editable ? (
            <fieldset className="flex flex-col gap-2">
              <legend className={ui.label}>{t("csvTitle")}</legend>
              <p className={ui.help}>{t("csvHint")}</p>
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("csvFile")}</span>
                  <input className={ui.input} type="file" accept=".csv,text/csv,text/plain" onChange={(e) => void readCsv(e.target.files?.[0] ?? null)} data-testid="hci-csv-file" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("delimiter")}</span>
                  <select className={ui.input} value={delimiter} onChange={(e) => { setDelimiter(e.target.value); setColumnMap({}); }}>
                    <option value=";">{t("semicolon")}</option>
                    <option value=",">{t("comma")}</option>
                    <option value={"\t"}>{t("tab")}</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={decimalComma} onChange={(e) => setDecimalComma(e.target.checked)} />
                  <span>{t("decimalComma")}</span>
                </label>
              </div>
              {headers.length > 0 ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {CSV_FIELDS.map((f) => (
                    <label key={f} className="flex flex-col gap-1">
                      <span className={ui.label}>{t(`field.${f}`)}</span>
                      <select className={ui.input} value={columnMap[f] ?? ""} onChange={(e) => setColumnMap((m) => ({ ...m, [f]: e.target.value }))} data-testid={`hci-col-${f}`}>
                        <option value="">{t("chooseColumn")}</option>
                        {headers.map((h) => (
                          <option key={h} value={h}>
                            {h}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              ) : null}
              <div>
                <button type="button" className={ui.secondary} disabled={busy || !csvComplete} onClick={() => void uploadCsv()}>
                  {t("csvUpload")}
                </button>
              </div>
            </fieldset>
          ) : null}

          <HeatingImportRowsForm
            key={`${selected.id}-${selected.rows.length}`}
            importId={selected.id}
            initial={selected.rows.map((r) => ({ user_number: r.user_number, heating_base: r.heating_base, heating_consumption: r.heating_consumption, hot_water_base: r.hot_water_base, hot_water_consumption: r.hot_water_consumption }))}
            editable={editable}
            onSaved={(d) => {
              if (d && typeof d === "object" && "id" in d && "rows" in d) replace(d as ImportRow);
            }}
          />

          {selected.rows.length > 0 ? (
            <div className="flex flex-col gap-2">
              <h4 className={ui.label}>{t("mappingTitle")}</h4>
              <div className="overflow-x-auto">
                <table className="mhvp-table">
                  <thead>
                    <tr>
                      <th>{t("field.user_number")}</th>
                      <th>{t("sum")}</th>
                      <th>{t("unit")}</th>
                      <th>{t("contract")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.rows.map((r) => {
                      const m = mapping[r.user_number] ?? { unit_id: "", contract_id: "" };
                      const sum = [r.heating_base, r.heating_consumption, r.hot_water_base, r.hot_water_consumption].reduce((a, v) => a + Math.round(Number(v) * 100), 0);
                      return (
                        <tr key={r.user_number}>
                          <td>{r.user_number}</td>
                          <td>{formatEur((sum / 100).toFixed(2))}</td>
                          <td>
                            <select className={ui.input} aria-label={`${t("unit")} ${r.user_number}`} disabled={!editable} value={m.unit_id} onChange={(e) => setMapping((x) => ({ ...x, [r.user_number]: { unit_id: e.target.value, contract_id: "" } }))}>
                              <option value="">{t("chooseUnit")}</option>
                              {units.map((u) => (
                                <option key={u.id} value={u.id}>
                                  {u.number}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <select className={ui.input} aria-label={`${t("contract")} ${r.user_number}`} disabled={!editable || !m.unit_id} value={m.contract_id} onChange={(e) => setMapping((x) => ({ ...x, [r.user_number]: { ...m, contract_id: e.target.value } }))}>
                              <option value="">{t("vacancy")}</option>
                              {contracts
                                .filter((c) => c.unit_id === m.unit_id)
                                .map((c) => (
                                  <option key={c.id} value={c.id}>
                                    {c.number}
                                  </option>
                                ))}
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {editable ? (
                <div>
                  <button type="button" className={ui.secondary} disabled={busy} onClick={() => void saveMapping()}>
                    {t("saveMapping")}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {editable ? (
            <div className="flex flex-col gap-2">
              <h4 className={ui.label}>{t("checkTitle")}</h4>
              {hasDuplicates ? (
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("duplicateReason")}</span>
                  <textarea className={ui.input} rows={2} minLength={10} value={ackReason} onChange={(e) => setAckReason(e.target.value)} data-testid="hci-ack" />
                </label>
              ) : null}
              <div>
                <button type="button" className={ui.primary} disabled={busy} onClick={() => void runCheck()}>
                  {t("check")}
                </button>
              </div>
            </div>
          ) : null}
          {selected.check_result ? (
            findings.length > 0 ? (
              <ul className={`${ui.alert} list-disc pl-6`} data-testid="hci-findings">
                {findings.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            ) : (
              <p className={ui.success} data-testid="hci-clean">
                {t("checkClean", { total: formatEur(selected.check_result.grand_total) })}
              </p>
            )
          ) : null}

          {editable && selected.status === "checked" ? (
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex min-w-64 flex-col gap-1">
                <span className={ui.label}>{t("targetStatement")}</span>
                <select className={ui.input} value={statementId} onChange={(e) => setStatementId(e.target.value)} data-testid="hci-statement">
                  <option value="">{t("chooseStatement")}</option>
                  {statements.map((s) => (
                    <option key={s.id} value={s.id}>
                      {formatDate(s.period_from)} bis {formatDate(s.period_to)} · V{s.version}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" className={ui.primary} disabled={busy || !statementId} onClick={() => void apply()}>
                {t("apply")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
