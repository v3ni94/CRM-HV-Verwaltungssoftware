"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type PreviewResult = {
  creditor_id: string | null;
  collection_date: string;
  count: number;
  control_sum: string;
  items: Record<string, unknown>[];
};

/** AF03 (GAF-04): Vorschau der einziehbaren Sollstellungen vor dem Lauf
 *  (`POST /accounting/direct-debits/preview`). Legt nichts an, bucht nichts, erzeugt keine Datei.
 *  Die Vorlaufzeit ist Pflichtparameter ohne Vorgabewert (OPEN_QUESTIONS M15-01 b). */
export function DirectDebitPreview({ ledgers }: { ledgers: { id: string; name: string }[] }) {
  const t = useTranslations("DirectDebitPreview");
  const [ledger, setLedger] = useState(ledgers[0]?.id ?? "");
  const [date, setDate] = useState("");
  const [lead, setLead] = useState("");
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const res = await bff<PreviewResult>("/api/bff/accounting/direct-debits/preview", {
      method: "POST",
      body: JSON.stringify({ ledger_id: ledger, collection_date: date, lead_days: Number(lead) }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };
  if (ledgers.length === 0) return null;
  return (
    <section aria-labelledby="dd-preview" className="flex flex-col gap-2">
      <h2 id="dd-preview" className="text-base font-semibold">
        {t("title")}
      </h2>
      <form onSubmit={run} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label>
          <span className={ui.label}>{t("ledger")}</span>
          <select className={ui.input} value={ledger} onChange={(e) => setLedger(e.target.value)}>
            {ledgers.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className={ui.label}>{t("collectionDate")}</span>
          <input type="date" required className={ui.input} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          <span className={ui.label}>{t("leadDays")}</span>
          <input
            type="number"
            min={0}
            max={60}
            required
            className={ui.input}
            value={lead}
            onChange={(e) => setLead(e.target.value)}
          />
        </label>
        <button type="submit" className={ui.button} disabled={busy}>
          {t("show")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <p role="status" className="text-sm">
          {t("result", {
            count: result.count,
            sum: formatEur(result.control_sum),
            date: formatDate(result.collection_date),
          })}
          {result.creditor_id ? "" : ` ${t("noCreditorId")}`}
        </p>
      ) : null}
    </section>
  );
}
