"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { API, ROW_STATUSES, type Reconciliation, type RowStatus, type RunReport, type StagingRow } from "@/lib/immoware";
import { ui } from "@/lib/ui";

export function StatusCounts({ counts, testId }: { counts: Record<string, number>; testId?: string }) {
  const t = useTranslations("Immoware24");
  const entries = Object.entries(counts);
  if (entries.length === 0) return <p className="text-sm text-muted">{t("noRows")}</p>;
  return (
    <dl className="flex flex-wrap gap-4 text-sm" data-testid={testId}>
      {entries.map(([status, n]) => (
        <div key={status} className="flex flex-col">
          <dt className="text-xs text-muted">{t.has(`rowStatus.${status}`) ? t(`rowStatus.${status}`) : status}</dt>
          <dd className="font-semibold">{n}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Step 4: counts per status and the rows of the selected status with their errors. */
export function ValidationReport({ sourceId, counts }: { sourceId: string; counts: Record<string, number> }) {
  const t = useTranslations("Immoware24");
  const [status, setStatus] = useState<RowStatus | "">(counts.invalid ? "invalid" : "");
  const [rows, setRows] = useState<StagingRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ limit: "200" });
    if (status) query.set("status", status);
    void bff<StagingRow[]>(`${API}/files/${sourceId}/rows?${query}`).then((res) => {
      if (!active) return;
      if (res.ok) {
        setRows(res.data);
        setError(null);
      } else setError(res.message);
    });
    return () => {
      active = false;
    };
  }, [sourceId, status]);

  return (
    <div className="flex flex-col gap-3">
      <StatusCounts counts={counts} testId="validation-counts" />
      <label className="flex max-w-xs flex-col gap-1">
        <span className={ui.label}>{t("filterStatus")}</span>
        <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value as RowStatus | "")}>
          <option value="">{t("filterAll")}</option>
          {ROW_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`rowStatus.${s}`)}
            </option>
          ))}
        </select>
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows === null ? null : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("noRows")}</p>
      ) : (
        <div className="overflow-x-auto">
<table className="mhvp-table" data-testid="validation-rows">
          <thead>
            <tr>
              <th>{t("colRow")}</th>
              <th>{t("colStatus")}</th>
              <th>{t("colErrors")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.row_number} className="border-b border-border align-top">
                <td>{r.row_number}</td>
                <td>{t(`rowStatus.${r.status}`)}</td>
                <td>
                  {r.errors.length ? (
                    <ul className="list-inside list-disc">
                      {r.errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
    </div>
  );
}

/** Steps 5 and 6: counts, problems and payment sums of a test run or an apply. */
export function RunReportView({ report, testId }: { report: RunReport; testId?: string }) {
  const t = useTranslations("Immoware24");
  return (
    <div className="flex flex-col gap-3" data-testid={testId}>
      <StatusCounts counts={report.counts} />
      {report.sums ? (
        <dl className="flex flex-wrap gap-4 text-sm" data-testid="payment-sums">
          <div className="flex flex-col">
            <dt className="text-xs text-muted">{t("sumSource")}</dt>
            <dd className="font-semibold">{formatEur(report.sums.source_gross)}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs text-muted">{t("sumCreated")}</dt>
            <dd className="font-semibold">{formatEur(report.sums.created_gross)}</dd>
          </div>
        </dl>
      ) : null}
      {report.problems.length> 0 ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("colRow")}</th>
              <th>{t("colStatus")}</th>
              <th>{t("colProblems")}</th>
            </tr>
          </thead>
          <tbody>
            {report.problems.map((p) => (
              <tr key={p.row} className="border-b border-border align-top">
                <td>{p.row}</td>
                <td>{t.has(`rowStatus.${p.status}`) ? t(`rowStatus.${p.status}`) : p.status}</td>
                <td>{p.messages.join("; ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : (
        <p className="text-sm text-muted">{t("noProblems")}</p>
      )}
    </div>
  );
}

/** Reconciliation after apply: status counts, units per property with differences, open differences. */
export function ReconciliationView({ data }: { data: Reconciliation }) {
  const t = useTranslations("Immoware24");
  const units = data.units_per_property ? Object.entries(data.units_per_property) : [];
  return (
    <div className="flex flex-col gap-3" data-testid="reconciliation">
      <p className="text-sm">{t("reconRows", { count: data.rows })}</p>
      <StatusCounts counts={data.status} />
      <p className={data.open_differences> 0 ? ui.alert : ui.notice} data-testid="open-differences">
        {t("openDifferences", { count: data.open_differences })}
      </p>
      {units.length> 0 ? (
        <div className="overflow-x-auto">
<table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("colProperty")}</th>
              <th className="num">{t("colFile")}</th>
              <th className="num">{t("colPlatform")}</th>
              <th className="num">{t("colDifference")}</th>
            </tr>
          </thead>
          <tbody>
            {units.map(([number, u]) => (
              <tr
                key={number}
                className={`border-b border-border ${u.difference !== 0 ? "bg-danger-bg text-danger-fg" : ""}`}
                data-difference={u.difference !== 0 ? "true" : undefined}
>
                <td>{number}</td>
                <td className="text-right">{u.file}</td>
                <td className="text-right">{u.platform}</td>
                <td className="text-right">{u.difference> 0 ? `+${u.difference}` : u.difference}</td>
              </tr>
            ))}
          </tbody>
        </table>
</div>
      ) : null}
    </div>
  );
}
