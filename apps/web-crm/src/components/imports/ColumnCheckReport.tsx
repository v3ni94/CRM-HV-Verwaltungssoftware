"use client";

import { useTranslations } from "next-intl";

import type { CheckSampleRow, ColumnCheck } from "@/lib/immoware";
import { ui } from "@/lib/ui";

type Props = { report: ColumnCheck };

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function SampleTable({ rows, fields, testId }: { rows: CheckSampleRow[]; fields: ColumnCheck["fields"]; testId: string }) {
  const t = useTranslations("Immoware24.detect");
  return (
    <div className={ui.tableScroll}>
      <table className={ui.table} data-testid={testId}>
        <thead>
          <tr>
            <th>{t("colRow")}</th>
            {fields.map((f) => (
              <th key={f.name}>{f.label}</th>
            ))}
            <th>{t("colMessages")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_number}>
              <td className={ui.num}>{row.row_number}</td>
              {fields.map((f) => (
                <td key={f.name}>{cell(row.values[f.name] ?? (f.header ? row.raw[f.header] : ""))}</td>
              ))}
              <td>{row.errors.length ? row.errors.join("; ") : t("noErrors")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Validation report of a mapping before it is saved (AE37): nothing is stored or imported. */
export function ColumnCheckReport({ report }: Props) {
  const t = useTranslations("Immoware24.detect");
  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="column-check-title" data-testid="column-check">
      <h3 id="column-check-title" className="text-base font-semibold">
        {t("checkTitle")}
      </h3>
      <p className="text-sm">{t("checkSummary", { rows: report.rows, valid: report.valid, invalid: report.invalid })}</p>
      <p className={report.ready ? ui.success : ui.alert} data-testid="column-check-ready">
        {report.ready ? t("ready") : t("notReady")}
      </p>
      {report.required.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="column-check-required">
            <caption className="text-left text-sm font-medium">{t("requiredTitle")}</caption>
            <thead>
              <tr>
                <th>{t("colField")}</th>
                <th>{t("colHeader")}</th>
                <th>{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {report.required.map((r) => (
                <tr key={r.name}>
                  <td>{r.label}</td>
                  <td>{r.header ?? ""}</td>
                  <td>
                    {t(`required.${r.status}`)}
                    {r.status === "partly_empty" ? ` (${t("emptyRows", { count: r.empty })})` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {report.fields.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="column-check-fields">
            <caption className="text-left text-sm font-medium">{t("fieldsTitle")}</caption>
            <thead>
              <tr>
                <th>{t("colField")}</th>
                <th>{t("colHeader")}</th>
                <th>{t("colFilled")}</th>
                <th>{t("colEmpty")}</th>
                <th>{t("colErrors")}</th>
                <th>{t("colExamples")}</th>
              </tr>
            </thead>
            <tbody>
              {report.fields.map((f) => (
                <tr key={f.name}>
                  <td>{f.label}</td>
                  <td>{f.header ?? ""}</td>
                  <td className={ui.num}>{f.filled}</td>
                  <td className={ui.num}>{f.empty}</td>
                  <td className={ui.num}>{f.errors}</td>
                  <td>{f.examples.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {report.not_in_file.length > 0 ? <p className={ui.alert}>{t("notInFile", { headers: report.not_in_file.join(", ") })}</p> : null}
      {report.assigned_twice.length > 0 ? <p className={ui.notice}>{t("assignedTwice", { headers: report.assigned_twice.join(", ") })}</p> : null}
      {report.unassigned_headers.length > 0 ? (
        <p className="text-sm text-muted">{t("unassigned", { headers: report.unassigned_headers.join(", ") })}</p>
      ) : null}
      {report.sample_rows.length > 0 && report.fields.length > 0 ? (
        <>
          <h4 className="text-sm font-medium">{t("samplesTitle")}</h4>
          <SampleTable rows={report.sample_rows} fields={report.fields} testId="column-check-samples" />
        </>
      ) : null}
      {report.error_rows.length > 0 ? (
        <>
          <h4 className="text-sm font-medium">{t("errorRowsTitle")}</h4>
          <SampleTable rows={report.error_rows} fields={report.fields} testId="column-check-errors" />
        </>
      ) : null}
    </section>
  );
}
