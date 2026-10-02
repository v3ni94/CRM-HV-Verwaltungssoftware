"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { VIEWS, buildQuery, toTable, type Column, type ReportHeader, type Table, type ViewId } from "./reportViews";

export type PropertyOption = { id: string; label: string };
export type ExplorerAccount = { id: string; number: string; name: string; category: string };

type Loaded = { header: ReportHeader; table: Table };

function cell(column: Column, value: string): string {
  if (column.kind === "money") return formatEur(value);
  if (column.kind === "date") return formatDate(value);
  return value;
}

/** Kontenblatt, Saldenliste, OP-Liste mit Stichtag sowie Monatsmatrix, Soll/Ist,
 *  Bankkontoabrechnung und Steuerentwürfe (7.7, M18). Jede Ansicht zeigt die einheitlichen
 *  Kopfangaben und kann als Excel geladen werden. */
export function ReportsExplorer({
  ledgerId,
  accounts,
  defaultAsOf,
  defaultStart,
  defaultEnd,
  properties = [],
}: {
  ledgerId: string;
  accounts: ExplorerAccount[];
  defaultAsOf: string;
  defaultStart: string;
  defaultEnd: string;
  properties?: PropertyOption[];
}) {
  const t = useTranslations("Accounting.reports.explorer");
  const [view, setView] = useState<ViewId>("trialBalance");
  const [asOf, setAsOf] = useState(defaultAsOf);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [accountId, setAccountId] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  const config = VIEWS[view];
  const base = `/api/bff/accounting/ledgers/${ledgerId}`;
  const params = { asOf, start, end, accountId, propertyId };
  const needsAccount = config.needs.account === true;
  const pickable = needsAccount && view === "bankStatement" ? accounts.filter((a) => a.category === "bank" || a.category === "cash") : accounts;
  const labels = (key: string) => t(`cols.${key}`);

  const load = async () => {
    if (needsAccount && !accountId) {
      setError(t("pickAccount"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<Record<string, unknown>>(`${base}/${config.ledgerPath ? "" : "reports/"}${config.path}?${buildQuery(view, params)}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      setLoaded(null);
      return;
    }
    setLoaded({ header: res.data.header as ReportHeader, table: toTable(view, res.data, labels, (id) => properties.find((p) => p.id === id)?.label ?? id) });
  };

  const xlsxHref = config.xlsx ? `${base}/reports/xlsx?report=${config.xlsx}&${new URLSearchParams({ as_of: asOf, start, end }).toString()}` : null; // xlsx export has no object filter (API)
  const header = loaded?.header;
  const filters = header ? Object.entries(header.filters).map(([k, v]) => `${k}: ${String(v)}`).join(", ") : "";

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
        <div>
          <label htmlFor="explorer-view" className={ui.label}>
            {t("view")}
          </label>
          <select id="explorer-view" className={ui.input} value={view} onChange={(e) => { setView(e.target.value as ViewId); setLoaded(null); }}>
            {(Object.keys(VIEWS) as ViewId[]).map((v) => (
              <option key={v} value={v}>
                {t(`views.${v}`)}
              </option>
            ))}
          </select>
        </div>
        {config.needs.asOf ? (
          <div>
            <label htmlFor="explorer-asof" className={ui.label}>
              {t("asOf")}
            </label>
            <input id="explorer-asof" type="date" className={ui.input} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </div>
        ) : null}
        {config.needs.period ? (
          <>
            <div>
              <label htmlFor="explorer-start" className={ui.label}>
                {t("start")}
              </label>
              <input id="explorer-start" type="date" className={ui.input} value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div>
              <label htmlFor="explorer-end" className={ui.label}>
                {t("end")}
              </label>
              <input id="explorer-end" type="date" className={ui.input} value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </>
        ) : null}
      </div>
      {config.needs.property ? (
        <div>
          <label htmlFor="explorer-property" className={ui.label}>
            {t("property")}
          </label>
          <select id="explorer-property" className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">{t("allProperties")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {needsAccount ? (
        <div>
          <label htmlFor="explorer-account" className={ui.label}>
            {t("account")}
          </label>
          <select id="explorer-account" className={ui.input} value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">{t("pickAccount")}</option>
            {pickable.map((a) => (
              <option key={a.id} value={a.id}>
                {a.number} {a.name}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className={ui.button} onClick={load} disabled={busy}>
          {busy ? t("loading") : t("show")}
        </button>
        {xlsxHref ? (
          <a className={ui.button} href={xlsxHref} download>
            {t("xlsx")}
          </a>
        ) : null}
        <a className={ui.button} href={`${base}/procedure-documentation?download=true`} download>
          {t("procedureDoc")}
        </a>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {loaded && header ? (
        <div className="flex flex-col gap-3" data-testid="explorer-result">
          <dl className="grid gap-x-6 gap-y-1 rounded-md border border-border bg-surface p-3 text-sm sm:grid-cols-2" data-testid="report-header">
            <div><dt className="text-muted">{t("head.entity")}</dt><dd>{header.legal_entity_name}</dd></div>
            <div><dt className="text-muted">{t("head.period")}</dt><dd>{header.period_start ? `${formatDate(header.period_start)} ${t("head.to")} ${formatDate(header.period_end)}` : t("head.none")}</dd></div>
            <div><dt className="text-muted">{t("head.asOf")}</dt><dd>{header.as_of ? formatDate(header.as_of) : t("head.none")}</dd></div>
            <div><dt className="text-muted">{t("head.generated")}</dt><dd>{formatDateTime(header.generated_at)}</dd></div>
            <div><dt className="text-muted">{t("head.filters")}</dt><dd>{filters || t("head.none")}</dd></div>
            <div><dt className="text-muted">{t("head.status")}</dt><dd>{header.status === "draft" ? t("head.draft") : header.status}</dd></div>
          </dl>
          <p className="text-xs text-muted">{header.status_note}</p>
          {loaded.table.summary.length > 0 ? (
            <ul className="flex flex-wrap gap-4 text-sm">
              {loaded.table.summary.map((s) => (
                <li key={s.label}>
                  <span className="text-muted">{s.label}: </span>
                  <span className="tabular-nums">{s.kind === "money" ? formatEur(s.value) : s.value}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {loaded.table.rows.length === 0 ? (
            <EmptyState title={t("empty")} />
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    {loaded.table.columns.map((c) => (
                      <th key={c.key} className={c.kind === "money" ? "num" : undefined}>
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loaded.table.rows.map((r, i) => (
                    <tr key={i}>
                      {loaded.table.columns.map((c) => (
                        <td key={c.key} className={c.kind === "money" ? "num" : undefined}>
                          {cell(c, r[c.key] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {loaded.table.notes.map((n) => (
            <p key={n} className="text-xs text-muted">
              {n}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}
