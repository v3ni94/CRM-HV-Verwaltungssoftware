"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Finding = { area: string; code: string; message: string };
type FactualCheck = {
  findings: Finding[];
  suggested_reviewer_user_id: string | null;
  price_tolerance_percent: string;
  quantity_tolerance_percent: string;
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
