"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type HashMismatch = { source_id: string; crm: string; objektakte: string };

export type ObjectReport = {
  object_number: string;
  objektakte_count: number;
  crm_count: number;
  missing_in_crm: string[];
  missing_in_crm_total: number;
  missing_in_objektakte: string[];
  missing_in_objektakte_total: number;
  hash_mismatches: HashMismatch[];
  hash_mismatch_total: number;
  placeholders: number;
  ok: boolean;
};

export type ReconciliationReport = {
  generated_at: string;
  ok: boolean;
  totals: {
    objects: number;
    objektakte_documents: number;
    crm_documents: number;
    missing_in_crm: number;
    missing_in_objektakte: number;
    hash_mismatches: number;
    placeholders: number;
    objects_with_differences: number;
  };
  objects: ObjectReport[];
  scope?: { number: string | null };
};

const PATH = "/api/bff/objektakte/reconciliation";

function idList(ids: string[], total: number, more: string): string {
  if (total === 0) return "";
  const shown = ids.join(", ");
  return total > ids.length ? `${shown} ${more}` : shown;
}

/** M35 Stufe 5, Parallelbetrieb: Abgleichbericht objektakte gegen CRM (Dokumente je Objekt,
 * fehlende Dokumente auf beiden Seiten, abweichende Prüfsummen). Nur lesend; eine Abweichung
 * wird über den Differenzimport oder von Hand aufgelöst. Spiegelt
 * `GET /api/v1/objektakte/reconciliation`. */
export function ReconciliationReport() {
  const t = useTranslations("Objektakte.reconciliation");
  const [number, setNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [onlyDifferences, setOnlyDifferences] = useState(true);

  const load = async () => {
    setBusy(true);
    setError(null);
    const params = new URLSearchParams();
    if (number.trim()) params.set("number", number.trim());
    const query = params.toString();
    const res = await bff<ReconciliationReport>(query ? `${PATH}?${query}` : PATH);
    setBusy(false);
    if (res.ok) setReport(res.data);
    else setError(res.message);
  };

  const rows = report ? report.objects.filter((o) => !onlyDifferences || !o.ok) : [];

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("number")}</span>
          <input
            className={ui.input}
            value={number}
            disabled={busy}
            placeholder="291"
            maxLength={16}
            onChange={(e) => setNumber(e.target.value)}
          />
        </label>
        <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => void load()}>
          {busy ? t("loading") : t("load")}
        </button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyDifferences} onChange={(e) => setOnlyDifferences(e.target.checked)} />
          {t("onlyDifferences")}
        </label>
      </div>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {report ? (
        <>
          <p className={report.ok ? ui.success : ui.notice} data-testid="reconciliation-summary">
            {report.ok
              ? t("summaryOk", { objects: report.totals.objects })
              : t("summaryDifferences", {
                  objects: report.totals.objects_with_differences,
                  total: report.totals.objects,
                })}{" "}
            {t("generatedAt", { at: formatDateTime(report.generated_at) })}
          </p>
          <dl className="grid gap-2 text-sm sm:grid-cols-4" data-testid="reconciliation-totals">
            <div className="flex flex-col">
              <dt className={ui.label}>{t("objektakteDocuments")}</dt>
              <dd className={ui.num}>{report.totals.objektakte_documents}</dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("crmDocuments")}</dt>
              <dd className={ui.num}>{report.totals.crm_documents}</dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("missingInCrm")}</dt>
              <dd className={ui.num}>{report.totals.missing_in_crm}</dd>
            </div>
            <div className="flex flex-col">
              <dt className={ui.label}>{t("hashMismatches")}</dt>
              <dd className={ui.num}>{report.totals.hash_mismatches}</dd>
            </div>
          </dl>
          {rows.length === 0 ? (
            <p className={ui.help}>{t("noRows")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className={ui.table} data-testid="reconciliation-table">
                <thead>
                  <tr>
                    <th scope="col">{t("colObject")}</th>
                    <th scope="col" className="num">
                      {t("colObjektakte")}
                    </th>
                    <th scope="col" className="num">
                      {t("colCrm")}
                    </th>
                    <th scope="col">{t("colMissingInCrm")}</th>
                    <th scope="col">{t("colMissingInObjektakte")}</th>
                    <th scope="col">{t("colHashMismatches")}</th>
                    <th scope="col" className="num">
                      {t("colPlaceholders")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((o) => (
                    <tr key={o.object_number} data-ok={o.ok ? "true" : "false"}>
                      <td>{o.object_number === "ohne_objekt" ? t("noObject") : o.object_number}</td>
                      <td className="num">{o.objektakte_count}</td>
                      <td className="num">{o.crm_count}</td>
                      <td>
                        {o.missing_in_crm_total > 0
                          ? `${o.missing_in_crm_total}: ${idList(o.missing_in_crm, o.missing_in_crm_total, t("more"))}`
                          : "0"}
                      </td>
                      <td>
                        {o.missing_in_objektakte_total > 0
                          ? `${o.missing_in_objektakte_total}: ${idList(o.missing_in_objektakte, o.missing_in_objektakte_total, t("more"))}`
                          : "0"}
                      </td>
                      <td>
                        {o.hash_mismatch_total > 0
                          ? `${o.hash_mismatch_total}: ${idList(
                              o.hash_mismatches.map((m) => m.source_id),
                              o.hash_mismatch_total,
                              t("more"),
                            )}`
                          : "0"}
                      </td>
                      <td className="num">{o.placeholders}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
