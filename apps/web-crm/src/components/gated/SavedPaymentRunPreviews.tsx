"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

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

  const load = useCallback(async () => {
    const res = await bff<SavedPreview[]>(`${BASE}?limit=20`);
    if (res.ok) {
      setRows(res.data);
      setError(null);
    } else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="saved-payment-run-previews">
      <h3 className="text-sm font-semibold">{t("title")}</h3>
      <GatedAction gate="G2" url={BASE} label={t("save")} hint={t("hint")} lockedText={t("locked")} onDone={() => void load()} testId="saved-preview-save" />
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
                trigger: r.trigger === "manual" ? t("triggerManual") : t("triggerScheduled"),
                count: r.summary?.invoice_count ?? 0,
              })}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
