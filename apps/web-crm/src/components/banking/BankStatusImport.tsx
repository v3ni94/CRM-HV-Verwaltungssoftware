"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ReportLine = {
  end_to_end_id: string | null;
  reported: string;
  reason_code: string | null;
  amount: string | null;
  result: string;
};
type Report = { id: string; kind: string; created: boolean; result: ReportLine[] };

/** Import of a bank status report (M15-02): pain.002 or camt.054 as XML file. Status only;
 *  nothing is posted, returns are corrected by a person (reversal). A repeated file has no
 *  effect. */
export function BankStatusImport() {
  const t = useTranslations("PaymentRun");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const xml = await file.text();
    const res = await bff<Report>("/api/bff/accounting/payment-runs/bank-status-reports", {
      method: "POST",
      body: JSON.stringify({ xml }),
    });
    setBusy(false);
    if (res.ok) setReport(res.data);
    else setError(res.message);
  };

  return (
    <section className={ui.card} aria-label={t("importTitle")}>
      <h2 className="text-base font-semibold">{t("importTitle")}</h2>
      <p className={ui.help}>{t("importHelp")}</p>
      <label className="mt-2 block">
        <span className={ui.label}>{t("importFile")}</span>
        <input
          type="file"
          accept=".xml,application/xml,text/xml"
          disabled={busy}
          onChange={(e) => void upload(e.target.files?.[0])}
        />
      </label>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report ? (
        <div className="mt-2" role="status">
          <p className="text-sm">
            {report.kind}: {report.created ? t("importDone", { n: report.result.length }) : t("importRepeated")}
          </p>
          <ul className="text-xs">
            {report.result.map((r, i) => (
              <li key={`${r.end_to_end_id ?? "x"}-${i}`}>
                {r.end_to_end_id ?? "?"} {r.reported}
                {r.reason_code ? ` (${r.reason_code})` : ""}: {r.result}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
