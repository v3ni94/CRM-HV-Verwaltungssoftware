"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** ADR 0010, M7-04: learning examples from ticket resolutions (`ai_example`, task
 *  `ticket_resolution`) are stored only while `tenant_settings.ai_learning_examples_enabled`
 *  is on (`PATCH /tenant/settings`, default off). Switching off stops new examples; existing
 *  rows stay until a retention rule is decided. Every change is written to the event log as
 *  `tenant_settings.updated`. */
export function AiLearningExamples({ initial, canUpdate }: { initial: boolean; canUpdate: boolean }) {
  const t = useTranslations("AiLearningExamples");
  const [enabled, setEnabled] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function toggle(next: boolean) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ ai_learning_examples_enabled: boolean }>("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({ ai_learning_examples_enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(res.data.ai_learning_examples_enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="ai-learning-examples-title">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="ai-learning-examples-title" className={ui.h2}>
            {t("title")}
          </h2>
          <span
            className={`rounded-md px-2 py-0.5 text-xs font-medium ${enabled ? "bg-warning-bg text-warning-fg" : "bg-surface text-muted"}`}
            data-testid="ai-learning-examples-status"
          >
            {enabled ? t("status.on") : t("status.off")}
          </span>
        </div>
        <p className={ui.help}>{t("description")}</p>
        <p className="text-xs text-warning-fg">{t("risk")}</p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={!canUpdate || busy} onChange={(e) => void toggle(e.target.checked)} />
          <span>{t("label")}</span>
        </label>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
