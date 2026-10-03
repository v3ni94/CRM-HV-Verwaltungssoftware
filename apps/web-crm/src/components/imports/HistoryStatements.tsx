"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/immoware24/history";

export type HistStatement = {
  id: string;
  kind: string;
  period_start: string;
  period_end: string;
  version: number;
  unit_number: string;
  recipient: string | null;
  result_amount: string | null;
  sent_on: string | null;
};
export type HistResolution = { id: string; resolved_on: string; item_number: string; title: string; result: string; form: string };
export type HistCheck = {
  totals: { statements: number; resolutions: number; findings: number };
  properties: { property_id: string; property_number: string; statements: number; resolutions: number; findings: number }[];
  findings: { property_number: string; entity: string; entity_id: string; code: string; message: string }[];
};

/** Read only view of filed historical statements and resolutions with the check report
 *  (GAJ-501). Nothing is posted, corrected or sent. */
export function HistoryStatements({ properties }: { properties: { property_id: string; property_number: string; property_name: string }[] }) {
  const t = useTranslations("HistoryStatements");
  const [propertyId, setPropertyId] = useState("");
  const [statements, setStatements] = useState<HistStatement[] | null>(null);
  const [resolutions, setResolutions] = useState<HistResolution[] | null>(null);
  const [check, setCheck] = useState<HistCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    setError(null);
    const q = new URLSearchParams();
    if (propertyId) q.set("property_id", propertyId);
    const qs = q.toString() ? `?${q.toString()}` : "";
    const lq = new URLSearchParams(q);
    lq.set("limit", "100");
    const [s, r, c] = await Promise.all([
      bff<HistStatement[]>(`${API}/statements?${lq.toString()}`),
      bff<HistResolution[]>(`${API}/resolutions?${lq.toString()}`),
      bff<HistCheck>(`${API}/statements/check${qs}`),
    ]);
    setBusy(false);
    if (s.ok) setStatements(s.data);
    if (r.ok) setResolutions(r.data);
    if (c.ok) setCheck(c.data);
    const failed = [s, r, c].find((x) => !x.ok);
    if (failed && !failed.ok) setError(failed.message);
  };

  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select className={ui.input} value={propertyId} onChange={(e) => setPropertyId(e.target.value)}>
            <option value="">{t("allProperties")}</option>
            {properties.map((p) => (
              <option key={p.property_id} value={p.property_id}>
                {p.property_number} {p.property_name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void load()}>
          {t("load")}
        </button>
      </div>
      {check ? (
        <div className="mt-2" data-testid="history-check">
          <p className={check.totals.findings > 0 ? ui.alert : ui.notice}>
            {t("checkTotals", { statements: check.totals.statements, resolutions: check.totals.resolutions, findings: check.totals.findings })}
          </p>
          {check.findings.length === 0 ? (
            <p className={ui.help}>{t("noFindings")}</p>
          ) : (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("colProperty")}</th>
                    <th>{t("colEntity")}</th>
                    <th>{t("colCode")}</th>
                    <th>{t("colMessage")}</th>
                  </tr>
                </thead>
                <tbody>
                  {check.findings.map((f) => (
                    <tr key={`${f.entity_id}-${f.code}`}>
                      <td>{f.property_number}</td>
                      <td>{f.entity}</td>
                      <td>{f.code}</td>
                      <td>{f.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
      {statements ? (
        <div className="mt-2" data-testid="history-statements">
          <h3 className="text-sm font-medium">{t("statementsTitle")}</h3>
          {statements.length === 0 ? (
            <p className={ui.help}>{t("noStatements")}</p>
          ) : (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("colKind")}</th>
                    <th>{t("colPeriod")}</th>
                    <th>{t("colVersion")}</th>
                    <th>{t("colUnit")}</th>
                    <th>{t("colRecipient")}</th>
                    <th className="text-right">{t("colResult")}</th>
                    <th>{t("colSent")}</th>
                  </tr>
                </thead>
                <tbody>
                  {statements.map((s) => (
                    <tr key={s.id}>
                      <td>{t.has(`kind.${s.kind}`) ? t(`kind.${s.kind}`) : s.kind}</td>
                      <td>
                        {formatDate(s.period_start)} bis {formatDate(s.period_end)}
                      </td>
                      <td>{s.version}</td>
                      <td>{s.unit_number}</td>
                      <td>{s.recipient ?? ""}</td>
                      <td className="text-right">{s.result_amount === null ? "" : formatEur(s.result_amount)}</td>
                      <td>{s.sent_on ? formatDate(s.sent_on) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
      {resolutions ? (
        <div className="mt-2" data-testid="history-resolutions">
          <h3 className="text-sm font-medium">{t("resolutionsTitle")}</h3>
          {resolutions.length === 0 ? (
            <p className={ui.help}>{t("noResolutions")}</p>
          ) : (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("colDate")}</th>
                    <th>{t("colItem")}</th>
                    <th>{t("colTitle")}</th>
                    <th>{t("colOutcome")}</th>
                    <th>{t("colForm")}</th>
                  </tr>
                </thead>
                <tbody>
                  {resolutions.map((r) => (
                    <tr key={r.id}>
                      <td>{formatDate(r.resolved_on)}</td>
                      <td>{r.item_number}</td>
                      <td>{r.title}</td>
                      <td>{r.result}</td>
                      <td>{r.form}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
