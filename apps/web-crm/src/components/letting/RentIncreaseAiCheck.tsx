"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Severity = "low" | "medium" | "high";
type Finding = { field: string; description: string; severity: Severity };
type State = {
  ai_check_id: string | null;
  latest_run: { id: string; status: string; error: string | null } | null;
  latest: { id: string; proposed: { findings: Finding[]; overall: "unauffaellig" | "pruefen" | "kritisch"; summary: string } } | null;
};
const SEVERITY_CLASS: Record<Severity, string> = { low: ui.badge, medium: ui.badgeWarning, high: ui.badgeDanger };

/** KI-Plausibilität des Mieterhöhungsfalls (M26-01): hints with a severity only, never a
 *  release or a legal review; the case and its deterministic check stay unchanged. */
export function RentIncreaseAiCheck({ caseId, canStart }: { caseId: string; canStart: boolean }) {
  const t = useTranslations("Letting.aiCheck");
  const tCommon = useTranslations("Common");
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = `/api/bff/letting/rent-increases/${caseId}/ai-check`;

  useEffect(() => {
    void bff<State>(path).then((res) => (res.ok ? setState(res.data) : setError(res.message)));
  }, [path]);

  const start = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<State>(path, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setState(res.data);
  };

  const run = state?.latest_run;
  const proposed = state?.latest?.proposed;
  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="rent-ai-check">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("notice")}</p>
      {run && run.status !== "succeeded" ? <p role="status">{t("runStatus", { status: run.status, error: run.error ?? "" })}</p> : null}
      {proposed ? (
        <>
          <p>{t(`overall.${proposed.overall}`)}</p>
          {proposed.summary ? <p className="text-sm">{proposed.summary}</p> : null}
          <ul className="flex flex-col gap-1 text-sm">
            {proposed.findings.length === 0 ? <li className="text-sm text-muted">{tCommon("emptyList")}</li> : null}
            {proposed.findings.map((f, i) => (
              <li key={`${f.field}-${i}`}>
                <span className={SEVERITY_CLASS[f.severity]}>{t(`severity.${f.severity}`)}</span> {f.description}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {canStart ? (
        <div>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void start()}>
            {t("start")}
          </button>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
