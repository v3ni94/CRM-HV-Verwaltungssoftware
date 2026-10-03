"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { SavedFilters } from "@/components/workspace/SavedFilters";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { GatedAction } from "./GatedAction";

type SavedPreview = { id: string; as_of: string; trigger: string; summary: { invoice_count?: number; until?: string } };

const BASE = "/api/bff/accounting/payment-runs/previews";

/**
 * GAI-401 (AJ28): stored payment run previews. Reading stays possible; saving a new preview is
 * held behind G2 until the management decides whether stored previews are needed before G2
 * (AJ28-01). A preview never creates orders or files.
 */
export function SavedPaymentRunPreviews() {
  const t = useTranslations("gatedMasks.savedPreviews");
  const [rows, setRows] = useState<SavedPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // AL05 (GAI-110): filters of the stored previews (exact reference date, trigger).
  const [asOf, setAsOf] = useState("");
  const [trigger, setTrigger] = useState("");

  const load = useCallback(async () => {
    const query = new URLSearchParams({ limit: "20" });
    if (asOf) query.set("as_of", asOf);
    if (trigger) query.set("trigger", trigger);
    const res = await bff<SavedPreview[]>(`${BASE}?${query}`);
    if (res.ok) {
      setRows(res.data);
      setError(null);
    } else setError(res.message);
  }, [asOf, trigger]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="saved-payment-run-previews">
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <GatedAction gate="G2" url={BASE} label={t("save")} hint={t("hint")} lockedText={t("locked")} onDone={() => void load()} testId="saved-preview-save" />
      <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="preview-filters">
        <label htmlFor="preview-as-of" className="text-muted">
          {t("filterAsOf")}
        </label>
        <input id="preview-as-of" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className={`${ui.input} w-auto`} />
        <label htmlFor="preview-trigger" className="text-muted">
          {t("filterTrigger")}
        </label>
        <select id="preview-trigger" value={trigger} onChange={(e) => setTrigger(e.target.value)} className={`${ui.input} w-auto`}>
          <option value="">{t("filterAll")}</option>
          <option value="manual">{t("triggerManual")}</option>
          <option value="schedule">{t("triggerScheduled")}</option>
          <option value="failed">{t("triggerFailed")}</option>
        </select>
      </div>
      <SavedFilters
        resource="payment_runs"
        basePath="/bank/zahllauf"
        current={Object.fromEntries(Object.entries({ as_of: asOf, trigger }).filter(([, v]) => v !== ""))}
        onApply={(p) => {
          setAsOf(p.as_of ?? "");
          setTrigger(p.trigger ?? "");
        }}
      />
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows && rows.length === 0 ? <p className={ui.help}>{t("empty")}</p> : null}
      {rows && rows.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((r) => (
            <li key={r.id}>
              {t("row", {
                asOf: formatDate(r.as_of),
                trigger: r.trigger === "manual" ? t("triggerManual") : r.trigger === "failed" ? t("triggerFailed") : t("triggerScheduled"),
                count: r.summary?.invoice_count ?? 0,
              })}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
