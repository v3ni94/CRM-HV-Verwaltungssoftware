"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type Event = { id: string; job_id: string; status: string; source: string; detail: string | null; occurred_at: string | null };

/** Verlauf eines Postversands (GAL-307, M23): Statushistorie der Zustellung beim Postdienst.
 *  Anzeige ohne Rechtswirkung; der Zustellnachweis bleibt der erfasste Beleg. */
export function DispatchHistory({ dispatchId }: { dispatchId: string }) {
  const t = useTranslations("Dispatch");
  const [events, setEvents] = useState<Event[] | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setError(null);
    const res = await bff<Event[]>(`/api/bff/postal/dispatches/${dispatchId}/history`);
    if (res.ok) setEvents(res.data);
    else setError(res.message);
  }

  return (
    <div className="mt-2 flex flex-col gap-2">
      <button type="button" className={ui.buttonSm} aria-expanded={open} onClick={() => void toggle()}>
        {open ? t("historyHide") : t("historyShow")}
      </button>
      {open ? (
        <div className="text-sm" data-testid="dispatch-history">
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : events === null ? (
            <p className="text-muted">{t("historyLoading")}</p>
          ) : events.length === 0 ? (
            <p className="text-muted">{t("historyNone")}</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {events.map((e) => (
                <li key={e.id} className="text-xs">
                  {formatDateTime(e.occurred_at)} · {e.status} · {e.source}
                  {e.detail ? ` · ${e.detail}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
