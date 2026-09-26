"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

const POLL_MS = 2000;

type Severity = "low" | "medium" | "high";
type Finding = { field: string; description: string; severity: Severity; position: string | null; unit: string | null };
type Proposed = {
  findings: Finding[];
  overall: "unauffaellig" | "pruefen" | "kritisch";
  summary: string;
  snapshot_hash: string | null;
  model: string | null;
};
type Proposal = { id: string; created_at: string; proposed: Proposed };
type Run = { id: string; status: string; error: string | null };
type State = { latest_run: Run | null; latest: Proposal | null; proposals: Proposal[] };

const SEVERITY_CLASS: Record<Severity, string> = {
  low: ui.badge,
  medium: ui.badgeWarning,
  high: ui.badgeDanger,
};
const OVERALL_CLASS: Record<Proposed["overall"], string> = {
  unauffaellig: ui.badgeSuccess,
  pruefen: ui.badgeWarning,
  kritisch: ui.badgeDanger,
};

/** Card "KI-Plausibilität" at a statement draft (A35): starts the check_statement run and
 *  shows the latest proposal's findings with their severity. Hints only; nothing here
 *  changes the statement (rule 0.1.6). `kind` selects the API path (M17 or M24). */
export function AiPlausibilityCard({ kind, id, snapshotHash }: { kind: "statements" | "hoa/statements"; id: string; snapshotHash: string | null }) {
  const t = useTranslations("Billing.aiCheck");
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const path = `/api/bff/${kind}/${id}/ai-check`;

  const load = useCallback(async () => {
    const res = await bff<State>(path);
    if (res.ok) {
      setState(res.data);
      setError(null);
      return res.data;
    }
    setError(res.message);
    return null;
  }, [path]);

  const pending = (s: State | null) => s?.latest_run != null && (s.latest_run.status === "queued" || s.latest_run.status === "running");

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const next = await load();
      if (cancelled) return;
      if (pending(next)) timer.current = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [load]);

  const start = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<State>(path, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setState(res.data);
    if (pending(res.data)) timer.current = setTimeout(async function poll() {
      const next = await load();
      if (pending(next)) timer.current = setTimeout(poll, POLL_MS);
    }, POLL_MS);
  };

  const latest = state?.latest ?? null;
  const run = state?.latest_run ?? null;
  const stale = latest !== null && snapshotHash !== null && latest.proposed.snapshot_hash !== snapshotHash;
  return (
    <section className={ui.card} aria-labelledby="ai-check-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ai-check-title" className={ui.h2}>
          {t("title")}
        </h2>
        <button type="button" className={ui.button} onClick={start} disabled={busy || !snapshotHash || pending(state)}>
          {t("start")}
        </button>
      </div>
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {pending(state) ? <p className="text-sm text-muted">{t("running")}</p> : null}
      {run && (run.status === "failed" || run.status === "blocked") && !pending(state) ? (
        <p role="alert" className={ui.alert}>
          {t("runFailed", { reason: run.error ?? "" })}
        </p>
      ) : null}
      {!latest && !pending(state) ? <p className="text-sm text-muted">{t("none")}</p> : null}
      {latest ? (
        <div className="mt-3 flex flex-col gap-2" data-testid="ai-check-result">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className={OVERALL_CLASS[latest.proposed.overall]}>{t(`overall.${latest.proposed.overall}`)}</span>
            <span className="text-muted">{t("checkedAt", { date: formatDate(latest.created_at) })}</span>
            {latest.proposed.snapshot_hash ? (
              <span className={stale ? ui.badgeWarning : ui.badge}>{t("snapshot", { hash: latest.proposed.snapshot_hash.slice(0, 8) })}</span>
            ) : null}
          </div>
          {latest.proposed.summary ? (
            <p className="text-sm">
              <span className="font-medium">{t("summary")}: </span>
              {latest.proposed.summary}
            </p>
          ) : null}
          {latest.proposed.findings.length === 0 ? (
            <p className="text-sm text-muted">{t("noFindings")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("findings")}</th>
                    <th>{t("reference")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {latest.proposed.findings.map((f, i) => (
                    <tr key={`${f.field}-${i}`}>
                      <td>{f.description}</td>
                      <td className="text-muted">
                        {[f.position ? t("position", { ref: f.position }) : null, f.unit ? t("unit", { unit: f.unit }) : null].filter(Boolean).join(", ")}
                      </td>
                      <td>
                        <span className={SEVERITY_CLASS[f.severity]}>{t(`severity.${f.severity}`)}</span>
                      </td>
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
