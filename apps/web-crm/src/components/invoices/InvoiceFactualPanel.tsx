"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Finding = { area: string; code: string; message: string };
type FactualCheck = {
  findings: Finding[];
  suggested_reviewer_user_id: string | null;
  price_tolerance_percent: string;
  quantity_tolerance_percent: string;
  budget?: {
    label: string;
    year: number;
    planned: string;
    booked_before: string;
    invoices_before?: string | null;
    credit_notes_before?: string | null;
    journal_lines_net?: string | null;
    invoice: string;
    remaining: string;
    exceeded: boolean;
  } | null;
  resolution?: {
    number: number;
    decided_on: string;
    status: string;
    subject: string;
    effective: boolean;
    subject_matches_plan: boolean | null;
  } | null;
};

const AREAS = ["order", "contract", "resolution", "budget", "recurring", "price", "quantity", "responsibility"];

/** Factual review of an incoming invoice (M14-02, 7.9.1 PÜ02): findings against order, service
 *  contract, resolution, budget and recurring plan, plus the proposed responsible property
 *  manager. Hints only: nothing here records a review step or releases the invoice. */
export function InvoiceFactualPanel({ invoiceId, managerName }: { invoiceId: string; managerName?: string | null }) {
  const t = useTranslations("InvoiceFactual");
  const [check, setCheck] = useState<FactualCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void bff<FactualCheck>(`/api/bff/accounting/invoices/${invoiceId}/factual-check`).then((result) => {
      if (!active) return;
      if (result.ok) setCheck(result.data);
      else setError(result.message);
    });
    return () => {
      active = false;
    };
  }, [invoiceId]);

  return (
    <section className={ui.card} data-testid="invoice-factual-panel">
      <h2 className={ui.h2}>{t("title")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : check === null ? (
        <p role="status" className="mt-2 text-sm text-muted">
          {t("loading")}
        </p>
      ) : (
        <>
          <p className={ui.help}>{t("hint")}</p>
          {check.findings.length === 0 ? (
            <p className="text-sm">{t("none")}</p>
          ) : (
            <ul className="list-inside list-disc text-sm">
              {check.findings.map((f, i) => (
                <li key={`${f.code}-${i}`}>
                  {AREAS.includes(f.area) ? t(`areas.${f.area}`) : f.area}: {f.message}
                </li>
              ))}
            </ul>
          )}
          {check.budget ? (
            <div className={ui.tableScroll}>
            <table className="mt-2 text-sm" data-testid="invoice-budget-table">
              <caption className="text-left font-medium">
                {t("budget.title", { label: check.budget.label, year: check.budget.year })}
              </caption>
              <tbody>
                {(["planned", "booked_before", "invoices_before", "credit_notes_before", "journal_lines_net", "invoice", "remaining"] as const)
                  .filter((k) => check.budget![k] != null)
                  .map((k) => (
                  <tr key={k}>
                    <th scope="row" className="pr-4 text-left font-normal">
                      {t(`budget.${k}`)}
                    </th>
                    <td className="text-right">{formatEur(check.budget![k] as string)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : null}
          {check.budget?.exceeded ? <p className="text-sm">{t("budget.exceeded")}</p> : null}
          {check.resolution ? (
            <p className="mt-2 text-sm" data-testid="invoice-resolution-coverage">
              {t("resolutionCoverage", {
                number: check.resolution.number,
                date: formatDate(check.resolution.decided_on),
                subject: check.resolution.subject,
              })}{" "}
              {check.resolution.effective ? t("resolutionEffective") : t("resolutionNotEffective")}
            </p>
          ) : null}
          <p className="mt-2 text-sm">
            {check.suggested_reviewer_user_id
              ? `${t("reviewer")}: ${managerName ?? check.suggested_reviewer_user_id}`
              : t("noReviewer")}
          </p>
          <p className={ui.help}>
            {t("tolerance", {
              price: Number(check.price_tolerance_percent).toLocaleString("de-DE"),
              quantity: Number(check.quantity_tolerance_percent).toLocaleString("de-DE"),
            })}
          </p>
        </>
      )}
    </section>
  );
}
