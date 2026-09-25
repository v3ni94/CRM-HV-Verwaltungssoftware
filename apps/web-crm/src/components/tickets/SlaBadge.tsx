"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type SlaColor = "green" | "yellow" | "red";
type ClockState = "running" | "paused" | "breached" | "done";

type SlaClock = {
  id: string;
  ticket_id: string;
  rule_id: string | null;
  started_at: string;
  due_response_at: string | null;
  due_resolution_at: string | null;
  first_response_at: string | null;
  resolved_at: string | null;
  state: ClockState;
  color: SlaColor;
};

const COLOR_CLASS: Record<SlaColor, string> = {
  green: ui.badgeSuccess,
  yellow: ui.badgeWarning,
  red: ui.badgeDanger,
};

/** Remaining time to a due timestamp, or how far it was overshot; null once there is no due
 *  timestamp left to track (e.g. resolved). */
function remaining(dueAt: string | null): { minutes: number; overdue: boolean } | null {
  if (!dueAt) return null;
  const diffMs = new Date(dueAt).getTime() - Date.now();
  return { minutes: Math.round(Math.abs(diffMs) / 60000), overdue: diffMs < 0 };
}

export function SlaBadge({ ticketId, canManage }: { ticketId: string; canManage: boolean }) {
  const t = useTranslations("Sla");
  const [clock, setClock] = useState<SlaClock | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const res = await bff<SlaClock>(`/api/bff/sla/tickets/${ticketId}/sla`);
      if (!active) return;
      if (res.ok) setClock(res.data);
      setLoaded(true);
    })();
    return () => {
      active = false;
    };
  }, [ticketId]);

  if (!loaded || !clock) return null;

  const pauseOrResume = async () => {
    setBusy(true);
    setError(null);
    const action = clock.state === "paused" ? "resume" : "pause";
    const res = await bff<SlaClock>(`/api/bff/sla/clocks/${clock.id}/${action}`, { method: "POST" });
    setBusy(false);
    if (res.ok) setClock(res.data);
    else setError(res.message);
  };

  const responseDone = clock.first_response_at !== null;
  const targetDue = clock.state === "done" ? null : !responseDone ? clock.due_response_at : clock.due_resolution_at;
  const target = remaining(targetDue);

  return (
    <section className={`${ui.card} flex flex-col gap-2`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={COLOR_CLASS[clock.color]}>{t(`colors.${clock.color}`)}</span>
        <span className={ui.badge}>{t(`clockStates.${clock.state}`)}</span>
        {target ? (
          <span className="text-sm text-muted">
            {responseDone
              ? target.overdue
                ? t("badge.resolutionOverdue", { minutes: target.minutes })
                : t("badge.resolutionRemaining", { minutes: target.minutes })
              : target.overdue
                ? t("badge.responseOverdue", { minutes: target.minutes })
                : t("badge.responseRemaining", { minutes: target.minutes })}
          </span>
        ) : null}
        {clock.resolved_at ? (
          <span className="text-xs text-muted">{t("badge.resolvedAt", { at: formatDateTime(clock.resolved_at) })}</span>
        ) : null}
      </div>
      {canManage && clock.state !== "done" && clock.state !== "breached" ? (
        <div>
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void pauseOrResume()}>
            {clock.state === "paused" ? t("badge.resume") : t("badge.pause")}
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
