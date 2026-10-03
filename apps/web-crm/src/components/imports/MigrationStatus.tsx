"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { EmptyState } from "@/components/ui/EmptyState";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/migration";
const KINDS = ["account", "debtor", "creditor", "bank", "reserve"] as const;
const METRICS = ["kontosaldo", "debitoren_op", "kreditoren_op", "bankstand", "ruecklage", "journal"] as const;
const STEPS = ["journal_imported", "opening_balances_entered", "released", "posted", "reconciled", "switched"] as const;

export type LedgerStep = {
  id: string;
  name: string;
  legal_entity_id: string;
  legal_entity_kind: string;
  leading_system: string;
  migration_cutoff: string | null;
  journal_entries: number;
  journal_imported: boolean;
  opening_balance_id: string | null;
  opening_balances_status: string | null;
  opening_balances_entered: boolean;
  released: boolean;
  posted: boolean;
  reconciled: boolean;
  switched: boolean;
  switch_request_id: string | null;
};
export type PropertyStatus = {
  property_id: string;
  property_number: string;
  property_name: string;
  ledgers: LedgerStep[];
  report: { id: string; created_at: string; as_of: string; zero_difference: boolean; deviations: number; document_id: string | null } | null;
};
export type BalanceLine = {
  id?: string;
  kind: string;
  account_id: string;
  account_number?: string;
  account_name?: string;
  amount: string;
  text?: string | null;
};
export type OpeningBalances = {
  id: string;
  ledger_id: string;
  cutoff_date: string;
  status: string;
  entered_via: string;
  note: string | null;
  released_by: string | null;
  released_at: string | null;
  posted_at: string | null;
  journal_entry_id: string | null;
  total_debit: string;
  total_credit: string;
  lines: BalanceLine[];
};
export type ReportLine = {
  ledger_id: string | null;
  metric: string;
  key: string;
  label: string;
  source: string | null;
  platform: string | null;
  difference: string | null;
  deviates: boolean;
  hint: string | null;
};
export type Report = {
  id: string;
  created_at: string;
  as_of: string;
  zero_difference: boolean;
  compared: number;
  deviations: number;
  total_difference: string;
  document_id: string | null;
  lines: ReportLine[];
};
type Account = { id: string; number: string; name: string; category: string };
type JournalResult = { imported: number; existing: number; lines: number; invalid: number; other_property: number; other_year: number; unbalanced: string[]; unmatched_accounts: string[]; warnings: string[] };
type SwitchRequest = { id: string; ledger_id: string; status: string; requested_by: string; created_at: string };

export type Permissions = { canCreate: boolean; canUpdate: boolean; canApprove: boolean };

function Steps({ ledger, t }: { ledger: LedgerStep; t: ReturnType<typeof useTranslations> }) {
  return (
    <span className="flex flex-wrap gap-1" data-testid="migration-steps">
      {STEPS.map((step) => (
        <StatusPill key={step} label={t(`step.${step}`)} variant={ledger[step] ? "success" : "neutral"} />
      ))}
    </span>
  );
}

/** Migration from Immoware24 without parallel operation (6.9.10, M8-03): status per property,
 * migration journal, opening balances with four eyes release, reconciliation with zero
 * difference check and the switch of the leading system behind G1. */
export function MigrationStatus({ canCreate, canUpdate, canApprove }: Permissions) {
  const t = useTranslations("Migration");
  const [rows, setRows] = useState<PropertyStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ property: PropertyStatus; ledger: LedgerStep } | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<OpeningBalances | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [request, setRequest] = useState<SwitchRequest | null>(null);
  const [journalResult, setJournalResult] = useState<JournalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [cutoff, setCutoff] = useState("");
  const [sourceFileId, setSourceFileId] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [yearComplete, setYearComplete] = useState(false);
  const [draft, setDraft] = useState<BalanceLine[]>([]);
  const [newLine, setNewLine] = useState<BalanceLine>({ kind: "account", account_id: "", amount: "" });
  const [csv, setCsv] = useState<File | null>(null);
  const [onlyDeviations, setOnlyDeviations] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<PropertyStatus[]>(`${API}/status`);
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setError(res.message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openLedger = async (property: PropertyStatus, ledger: LedgerStep) => {
    setError(null);
    setNotice(null);
    setJournalResult(null);
    setSelected({ property, ledger });
    setCutoff(ledger.migration_cutoff ?? "");
    const [acc, bal, rep, req] = await Promise.all([
      bff<Account[]>(`/api/bff/accounting/ledgers/${ledger.id}/accounts`),
      bff<OpeningBalances[]>(`${API}/ledgers/${ledger.id}/opening-balances`),
      property.report ? bff<Report>(`${API}/reconciliation/${property.report.id}`) : Promise.resolve(null),
      ledger.switch_request_id ? bff<SwitchRequest[]>(`${API}/switch-requests?ledger_id=${ledger.id}`) : Promise.resolve(null),
    ]);
    setAccounts(acc.ok ? acc.data : []);
    const current = (bal.ok && bal.data.length > 0 ? bal.data[0] : null) ?? null;
    setBalances(current);
    setDraft(current && current.status === "draft" ? current.lines.map((l) => ({ ...l })) : []);
    setReport(rep && rep.ok ? rep.data : null);
    setRequest(req && req.ok ? (req.data.find((r) => r.status === "requested") ?? null) : null);
  };

  const refresh = async () => {
    await load();
    if (!selected) return;
    const res = await bff<PropertyStatus[]>(`${API}/status`);
    if (!res.ok) return;
    const property = res.data.find((p) => p.property_id === selected.property.property_id);
    const ledger = property?.ledgers.find((l) => l.id === selected.ledger.id);
    if (property && ledger) await openLedger(property, ledger);
  };

  const run = async (action: () => Promise<{ ok: boolean; message?: string }>, done: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await action();
    setBusy(false);
    if (res.ok) {
      setNotice(done);
      await refresh();
    } else setError(res.message ?? t("failed"));
  };

  const saveCutoff = () =>
    run(
      () => bff(`${API}/ledgers/${selected!.ledger.id}/cutoff`, { method: "PUT", body: JSON.stringify({ migration_cutoff: cutoff || null }) }),
      t("cutoffSaved"),
    );

  const importJournal = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<JournalResult>(`${API}/ledgers/${selected!.ledger.id}/journal`, {
      method: "POST",
      body: JSON.stringify({ source_file_id: sourceFileId.trim(), year: Number(year), year_complete: yearComplete }),
    });
    setBusy(false);
    if (res.ok) {
      setJournalResult(res.data);
      await refresh();
    } else setError(res.message);
  };

  const saveBalances = () =>
    run(
      () =>
        bff(`${API}/ledgers/${selected!.ledger.id}/opening-balances`, {
          method: "PUT",
          body: JSON.stringify({
            cutoff_date: cutoff,
            lines: draft.map((l) => ({ kind: l.kind, account_id: l.account_id, amount: l.amount, text: l.text ?? null })),
          }),
        }),
      t("balancesSaved"),
    );

  const uploadCsv = () =>
    run(async () => {
      const form = new FormData();
      form.append("cutoff_date", cutoff);
      form.append("file", csv!);
      const res = await bff<{ balances: OpeningBalances | null; errors: string[] }>(`${API}/ledgers/${selected!.ledger.id}/opening-balances/import`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) return res;
      if (!res.data.balances) return { ok: false, message: res.data.errors.join("; ") };
      return { ok: true };
    }, t("balancesImported"));

  const release = () => run(() => bff(`${API}/opening-balances/${balances!.id}/release`, { method: "POST", body: "{}" }), t("released"));
  const post = () => run(() => bff(`${API}/opening-balances/${balances!.id}/post`, { method: "POST" }), t("posted"));
  const reconcile = () =>
    run(() => bff(`${API}/properties/${selected!.property.property_id}/reconciliation`, { method: "POST", body: "{}" }), t("reconciled"));
  const requestSwitch = () => run(() => bff(`${API}/ledgers/${selected!.ledger.id}/switch-requests`, { method: "POST", body: "{}" }), t("switchRequested"));
  const decide = (approve: boolean) =>
    run(() => bff(`${API}/switch-requests/${request!.id}/${approve ? "approve" : "reject"}`, { method: "POST", body: "{}" }), t(approve ? "switchApproved" : "switchRejected"));

  const metricLabel = (metric: string) => ((METRICS as readonly string[]).includes(metric) ? t(`metric.${metric}`) : metric);
  const visibleLines = report ? report.lines.filter((line) => !onlyDeviations || line.deviates) : [];
  const editable = !balances || balances.status === "draft";

  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {rows === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <div data-testid="migration-empty">
          <EmptyState title={t("empty")} />
        </div>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="migration-list">
            <thead>
              <tr>
                <th>{t("colProperty")}</th>
                <th>{t("colLedger")}</th>
                <th>{t("colCutoff")}</th>
                <th>{t("colLeading")}</th>
                <th>{t("colSteps")}</th>
                <th>{t("colActions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.flatMap((property) =>
                property.ledgers.map((ledger) => (
                  <tr key={ledger.id} data-testid="migration-row">
                    <td>
                      {property.property_number} {property.property_name}
                    </td>
                    <td>{ledger.name}</td>
                    <td>{ledger.migration_cutoff ? formatDate(ledger.migration_cutoff) : t("noCutoff")}</td>
                    <td>{ledger.leading_system === "mhvp" ? t("leadingPlatform") : t("leadingImmoware")}</td>
                    <td>
                      <Steps ledger={ledger} t={t} />
                    </td>
                    <td>
                      <button type="button" className={ui.buttonSm} onClick={() => void openLedger(property, ledger)}>
                        {t("open")}
                      </button>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
      {selected ? (
        <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("detailTitle")} data-testid="migration-detail">
          <h2 className="text-sm font-semibold">
            {t("detailTitle")}: {selected.property.property_number} {selected.property.property_name}, {selected.ledger.name}
          </h2>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("cutoffTitle")}</h3>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("colCutoff")}</span>
                <input type="date" className={ui.input} value={cutoff} onChange={(e) => setCutoff(e.target.value)} disabled={!canUpdate || selected.ledger.posted} data-testid="migration-cutoff" />
              </label>
              {canUpdate && !selected.ledger.posted ? (
                <button type="button" className={ui.button} disabled={busy} onClick={() => void saveCutoff()}>
                  {t("saveCutoff")}
                </button>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("journalTitle")}</h3>
            <p className="text-sm text-muted">{t("journalCount", { count: selected.ledger.journal_entries })}</p>
            {canCreate ? (
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("sourceFileId")}</span>
                  <input className={ui.input} value={sourceFileId} onChange={(e) => setSourceFileId(e.target.value)} placeholder="UUID" data-testid="migration-source-file" />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("year")}</span>
                  <input type="number" className={ui.input} value={year} onChange={(e) => setYear(e.target.value)} />
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={yearComplete} onChange={(e) => setYearComplete(e.target.checked)} />
                  {t("yearComplete")}
                </label>
                <button type="button" className={ui.button} disabled={busy || !sourceFileId.trim()} onClick={() => void importJournal()} data-testid="migration-import-journal">
                  {t("importJournal")}
                </button>
              </div>
            ) : null}
            <p className={ui.help}>{t("journalHelp")}</p>
            {journalResult ? (
              <p className="text-sm" data-testid="migration-journal-result">
                {t("journalResult", {
                  imported: journalResult.imported,
                  existing: journalResult.existing,
                  invalid: journalResult.invalid + journalResult.other_property + journalResult.other_year,
                })}
                {journalResult.unmatched_accounts.length > 0 ? ` ${t("unmatchedAccounts", { accounts: journalResult.unmatched_accounts.join(", ") })}` : ""}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("balancesTitle")}</h3>
            {balances ? (
              <div className="flex flex-wrap items-center gap-3 text-sm" data-testid="migration-balances-status">
                <StatusPill label={t(`balanceStatus.${balances.status}`)} variant={balances.status === "posted" ? "success" : balances.status === "released" ? "warning" : "neutral"} />
                <span>
                  {t("colCutoff")} {formatDate(balances.cutoff_date)}
                </span>
                <span>
                  {t("totalDebit")} {formatEur(balances.total_debit)}, {t("totalCredit")} {formatEur(balances.total_credit)}
                </span>
                {balances.released_at ? <span>{t("releasedAt", { at: formatDateTime(balances.released_at) })}</span> : null}
              </div>
            ) : (
              <p className="text-sm text-muted">{t("noBalances")}</p>
            )}
            {balances && balances.status !== "draft" ? (
              <div className={ui.tableScroll}>
                <table className={ui.table} data-testid="migration-balance-lines">
                  <thead>
                    <tr>
                      <th>{t("colKind")}</th>
                      <th>{t("colAccount")}</th>
                      <th className="text-right">{t("colAmount")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balances.lines.map((line) => (
                      <tr key={line.id ?? line.account_id}>
                        <td>{t(`kind.${line.kind}`)}</td>
                        <td>
                          {line.account_number} {line.account_name}
                        </td>
                        <td className="text-right tabular-nums">{formatEur(line.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {canCreate && editable ? (
              <div className="flex flex-col gap-2" data-testid="migration-balance-form">
                {draft.length > 0 ? (
                  <ul className="flex flex-col gap-1 text-sm">
                    {draft.map((line, i) => {
                      const account = accounts.find((a) => a.id === line.account_id);
                      return (
                        <li key={`${line.account_id}-${i}`} className="flex flex-wrap items-center gap-2">
                          <span>{t(`kind.${line.kind}`)}</span>
                          <span className={ui.mono}>{account ? `${account.number} ${account.name}` : line.account_number}</span>
                          <span className="tabular-nums">{formatEur(line.amount)}</span>
                          <button type="button" className={ui.buttonSm} onClick={() => setDraft(draft.filter((_, j) => j !== i))}>
                            {t("removeLine")}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("colKind")}</span>
                    <select className={ui.input} value={newLine.kind} onChange={(e) => setNewLine({ ...newLine, kind: e.target.value })} data-testid="migration-line-kind">
                      {KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {t(`kind.${kind}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("colAccount")}</span>
                    <select className={ui.input} value={newLine.account_id} onChange={(e) => setNewLine({ ...newLine, account_id: e.target.value })} data-testid="migration-line-account">
                      <option value="">{t("chooseAccount")}</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.number} {a.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("colAmount")}</span>
                    <input className={ui.input} value={newLine.amount} onChange={(e) => setNewLine({ ...newLine, amount: e.target.value })} placeholder="1234.56" data-testid="migration-line-amount" />
                  </label>
                  <button
                    type="button"
                    className={ui.button}
                    disabled={!newLine.account_id || !/^-?\d+(\.\d{1,2})?$/.test(newLine.amount)}
                    onClick={() => {
                      setDraft([...draft, { ...newLine }]);
                      setNewLine({ kind: newLine.kind, account_id: "", amount: "" });
                    }}
                    data-testid="migration-line-add"
                  >
                    {t("addLine")}
                  </button>
                  <button type="button" className={ui.primary} disabled={busy || draft.length === 0 || !cutoff} onClick={() => void saveBalances()} data-testid="migration-balances-save">
                    {t("saveBalances")}
                  </button>
                </div>
                <p className={ui.help}>{t("amountHelp")}</p>
                <div className="flex flex-wrap items-end gap-3">
                  <label className="flex flex-col gap-1">
                    <span className={ui.label}>{t("csvFile")}</span>
                    <input type="file" accept=".csv,text/csv" className={ui.input} onChange={(e) => setCsv(e.target.files?.[0] ?? null)} />
                  </label>
                  <button type="button" className={ui.button} disabled={busy || !csv || !cutoff} onClick={() => void uploadCsv()}>
                    {t("importCsv")}
                  </button>
                  <span className={ui.help}>{t("csvHelp")}</span>
                </div>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {canApprove && balances && balances.status === "draft" ? (
                <button type="button" className={ui.button} disabled={busy} onClick={() => void release()} data-testid="migration-release">
                  {t("release")}
                </button>
              ) : null}
              {canCreate && balances && balances.status === "released" ? (
                <button type="button" className={ui.primary} disabled={busy} onClick={() => void post()} data-testid="migration-post">
                  {t("post")}
                </button>
              ) : null}
            </div>
            <p className={ui.help}>{t("releaseHelp")}</p>
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("reconciliationTitle")}</h3>
            <div className="flex flex-wrap items-center gap-3">
              {canCreate ? (
                <button type="button" className={ui.button} disabled={busy} onClick={() => void reconcile()} data-testid="migration-reconcile">
                  {t("reconcile")}
                </button>
              ) : null}
              {report ? (
                <>
                  <StatusPill label={report.zero_difference ? t("zeroDifference") : t("deviations", { count: report.deviations })} variant={report.zero_difference ? "success" : "danger"} />
                  <span className="text-sm text-muted">
                    {formatDateTime(report.created_at)}, {t("colCutoff")} {formatDate(report.as_of)}, {t("totalDifference")} {formatEur(report.total_difference)}
                  </span>
                  <a className="text-sm font-medium hover:underline" href={`${API}/reconciliation/${report.id}/pdf`} download>
                    {t("downloadPdf")}
                  </a>
                </>
              ) : null}
            </div>
            {report ? (
              <>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={onlyDeviations} onChange={(e) => setOnlyDeviations(e.target.checked)} />
                  {t("onlyDeviations")}
                </label>
                <div className={ui.tableScroll}>
                  <table className={ui.table} data-testid="migration-report-lines">
                    <thead>
                      <tr>
                        <th>{t("colMetric")}</th>
                        <th>{t("colKey")}</th>
                        <th>{t("colLabel")}</th>
                        <th className="text-right">{t("colSource")}</th>
                        <th className="text-right">{t("colPlatform")}</th>
                        <th className="text-right">{t("colDifference")}</th>
                        <th>{t("colHint")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleLines.map((line) => (
                        <tr key={`${line.ledger_id}-${line.metric}-${line.key}`} className={line.deviates ? "font-medium" : undefined}>
                          <td>{metricLabel(line.metric)}</td>
                          <td className={ui.mono}>{line.key}</td>
                          <td>{line.label}</td>
                          <td className="text-right tabular-nums">{line.source === null ? t("missing") : formatEur(line.source)}</td>
                          <td className="text-right tabular-nums">{line.platform === null ? t("missing") : formatEur(line.platform)}</td>
                          <td className="text-right tabular-nums">{line.difference === null ? "" : formatEur(line.difference)}</td>
                          <td className="text-muted">{line.hint ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted">{t("noReport")}</p>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">{t("switchTitle")}</h3>
            <p className={ui.help}>{t("switchHelp")}</p>
            {selected.ledger.switched ? (
              <p className={ui.success} data-testid="migration-switched">
                {t("switchedNote")}
              </p>
            ) : request ? (
              <div className="flex flex-wrap items-center gap-2" data-testid="migration-switch-pending">
                <span className="text-sm">{t("switchPending", { at: formatDateTime(request.created_at) })}</span>
                {canApprove ? (
                  <>
                    <button type="button" className={ui.primary} disabled={busy} onClick={() => void decide(true)} data-testid="migration-switch-approve">
                      {t("approveSwitch")}
                    </button>
                    <button type="button" className={ui.danger} disabled={busy} onClick={() => void decide(false)}>
                      {t("rejectSwitch")}
                    </button>
                  </>
                ) : null}
              </div>
            ) : canCreate ? (
              <button type="button" className={ui.button} disabled={busy} onClick={() => void requestSwitch()} data-testid="migration-switch-request">
                {t("requestSwitch")}
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
