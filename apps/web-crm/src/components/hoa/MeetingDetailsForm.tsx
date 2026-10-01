"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const MEETING_KINDS = ["ordinary", "extraordinary", "repeat", "continuation", "partial", "circular_resolution"] as const;
const AGENDA_RESULTS = new Set(["accepted", "rejected", "deferred", "no_vote"]);

export type MeetingDetails = {
  kind: string;
  scheduled_at: string;
  ends_at: string | null;
  origin_meeting_id: string | null;
  public_description: string | null;
  internal_description: string | null;
  invitation_template_id: string | null;
  proxy_template_id: string | null;
  ballot_template_id: string | null;
};

function toLocalInput(value: string | null): string {
  if (!value) return "";
  const d = new Date(value);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** GA03-01: Ende, Vorlagenbezüge sowie öffentliche (Portal) und interne Beschreibung der
 *  Versammlung. Die Art ist beim Anlegen festgelegt und wird hier nur angezeigt. */
export function MeetingDetailsForm({ meetingId, data, closed }: { meetingId: string; data: MeetingDetails; closed: boolean }) {
  const t = useTranslations("HoaWork.meetingDetails");
  const router = useRouter();
  const [endsAt, setEndsAt] = useState(toLocalInput(data.ends_at));
  const [pub, setPub] = useState(data.public_description ?? "");
  const [internal, setInternal] = useState(data.internal_description ?? "");
  const [templates, setTemplates] = useState({
    invitation_template_id: data.invitation_template_id ?? "",
    proxy_template_id: data.proxy_template_id ?? "",
    ballot_template_id: data.ballot_template_id ?? "",
  });
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const kindLabel = (MEETING_KINDS as readonly string[]).includes(data.kind) ? t(`kinds.${data.kind}`) : data.kind;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const ends = endsAt ? new Date(endsAt) : null;
    if (ends && ends <= new Date(data.scheduled_at)) {
      setState("error");
      setMessage(t("endBeforeStart"));
      return;
    }
    setState("saving");
    const result = await bff(`/api/bff/hoa/meetings/${meetingId}`, {
      method: "PATCH",
      body: JSON.stringify({
        ends_at: ends ? ends.toISOString() : null,
        public_description: pub.trim() || null,
        internal_description: internal.trim() || null,
        invitation_template_id: templates.invitation_template_id.trim() || null,
        proxy_template_id: templates.proxy_template_id.trim() || null,
        ballot_template_id: templates.ballot_template_id.trim() || null,
      }),
    });
    if (result.ok) {
      setState("saved");
      setMessage(null);
      router.refresh();
    } else {
      setState("error");
      setMessage(result.message);
    }
  }

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-labelledby="meeting-details-title" data-testid="meeting-details">
      <h2 id="meeting-details-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-sm">
        <span className={ui.label}>{t("kind")}: </span>
        <span data-testid="meeting-kind">{kindLabel}</span>
        {data.origin_meeting_id ? (
          <span className="text-muted"> · {t("origin")}: {data.origin_meeting_id}</span>
        ) : null}
      </p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("endsAt")}</span>
        <input className={`${ui.input} sm:w-64`} type="datetime-local" value={endsAt} disabled={closed} onChange={(e) => setEndsAt(e.target.value)} data-testid="meeting-ends-at" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("publicDescription")}</span>
        <textarea className={ui.input} rows={2} maxLength={20000} value={pub} disabled={closed} onChange={(e) => setPub(e.target.value)} data-testid="meeting-public-description" />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("internalDescription")}</span>
        <textarea className={ui.input} rows={2} maxLength={20000} value={internal} disabled={closed} onChange={(e) => setInternal(e.target.value)} data-testid="meeting-internal-description" />
      </label>
      <div className="grid gap-2 sm:grid-cols-3">
        {(["invitation_template_id", "proxy_template_id", "ballot_template_id"] as const).map((key) => (
          <label key={key} className="flex flex-col gap-1">
            <span className={ui.label}>{t(key.replace("_template_id", "Template"))}</span>
            <input
              className={ui.input}
              value={templates[key]}
              disabled={closed}
              onChange={(e) => setTemplates((prev) => ({ ...prev, [key]: e.target.value }))}
              data-testid={`meeting-${key}`}
            />
          </label>
        ))}
      </div>
      {closed ? null : (
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={state === "saving"}>
            {t("save")}
          </button>
        </div>
      )}
      {state === "saved" ? <p className={ui.success}>{t("saved")}</p> : null}
      {state === "error" && message ? (
        <p role="alert" className={ui.alert}>
          {message}
        </p>
      ) : null}
    </form>
  );
}

/** GA03-02: Ergebnis je TOP (angenommen und abgelehnt nur aus der Verkündung; vertagt und ohne
 *  Abstimmung werden hier erfasst) und Protokolltext. */
export function AgendaResultForm({
  itemId,
  result,
  minutesText,
  closed,
}: {
  itemId: string;
  result: string | null;
  minutesText: string | null;
  closed: boolean;
}) {
  const t = useTranslations("HoaWork.agendaResult");
  const router = useRouter();
  const [text, setText] = useState(minutesText ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const announced = result === "accepted" || result === "rejected";

  async function patch(body: Record<string, unknown>) {
    setState("saving");
    const res = await bff(`/api/bff/hoa/agenda/${itemId}`, { method: "PATCH", body: JSON.stringify(body) });
    if (res.ok) {
      setState("saved");
      setMessage(null);
      router.refresh();
    } else {
      setState("error");
      setMessage(res.message);
    }
  }

  return (
    <div className="mt-1 flex flex-col gap-1 text-sm" data-testid={`agenda-result-${itemId}`}>
      <span>
        <span className={ui.label}>{t("result")}: </span>
        {result && AGENDA_RESULTS.has(result) ? t(`results.${result}`) : t("none")}
      </span>
      {closed ? null : (
        <>
          {announced ? null : (
            <div className="flex flex-wrap gap-2">
              {result === "deferred" || result === "no_vote" ? (
                <button type="button" className={ui.button} disabled={state === "saving"} onClick={() => patch({ result: null })}>
                  {t("clearResult")}
                </button>
              ) : (
                (["deferred", "no_vote"] as const).map((r) => (
                  <button key={r} type="button" className={ui.button} disabled={state === "saving"} onClick={() => patch({ result: r })}>
                    {t("setResult")}: {t(`results.${r}`)}
                  </button>
                ))
              )}
            </div>
          )}
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("minutesText")}</span>
            <textarea className={ui.input} rows={2} maxLength={50000} value={text} onChange={(e) => setText(e.target.value)} data-testid={`minutes-text-${itemId}`} />
          </label>
          <div>
            <button type="button" className={ui.button} disabled={state === "saving"} onClick={() => patch({ minutes_text: text.trim() || null })}>
              {t("saveMinutes")}
            </button>
          </div>
        </>
      )}
      {state === "saved" ? <p className={ui.success}>{t("saved")}</p> : null}
      {state === "error" && message ? (
        <p role="alert" className={ui.alert}>
          {message}
        </p>
      ) : null}
    </div>
  );
}
