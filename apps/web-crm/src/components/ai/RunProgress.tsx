"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { isRunPending, POLL_INTERVAL_MS, type Run } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Polls GET /ai/runs/{id} every 2 s while the run is queued or running. */
export function useRunPolling(initial: Run, onDone?: (run: Run) => void) {
  const [run, setRun] = useState<Run>(initial);
  const [pollError, setPollError] = useState<string | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (!isRunPending(initial)) {
      done.current?.(initial);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      const res = await bff<Run>(`/api/bff/ai/runs/${initial.id}`);
      if (cancelled) return;
      if (res.ok) {
        setPollError(null);
        setRun(res.data);
        if (!isRunPending(res.data)) {
          done.current?.(res.data);
          return;
        }
      } else {
        setPollError(res.message);
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    };
    timer = setTimeout(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [initial]);

  return { run, pollError };
}

export function RunStatusView({ run, pollError }: { run: Run; pollError?: string | null }) {
  const t = useTranslations("Ai");
  if (isRunPending(run)) {
    return (
      <div role="status" aria-live="polite" className={`${ui.notice} flex items-center gap-2`}>
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-border border-t-accent" aria-hidden />
        <span>{run.status === "queued" ? t("runQueued") : t("runRunning")}</span>
        {pollError ? <span className="text-danger-fg">{pollError}</span> : null}
      </div>
    );
  }
  if (run.status === "blocked") {
    return (
      <div role="alert" className={ui.alert}>
        <p className="font-medium">{t("runBlocked")}</p>
        <p>{run.error || t("noReason")}</p>
      </div>
    );
  }
  if (run.status === "failed") {
    return (
      <div role="alert" className={ui.alert}>
        <p className="font-medium">{t("runFailed")}</p>
        <p>{run.error || t("noReason")}</p>
      </div>
    );
  }
  return null;
}

export function RunProgress({ run: initial, onDone }: { run: Run; onDone?: (run: Run) => void }) {
  const { run, pollError } = useRunPolling(initial, onDone);
  return <RunStatusView run={run} pollError={pollError} />;
}
