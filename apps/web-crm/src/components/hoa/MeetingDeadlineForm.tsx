"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Resolution deadline of a virtual owners' meeting (M9-07): date plus mandatory source,
 *  entered and never computed; shown in the deadline list (A41) as orientation. */
export function MeetingDeadlineForm({
  meetingId,
  deadline,
  source,
}: {
  meetingId: string;
  deadline: string | null;
  source: string | null;
}) {
  const t = useTranslations("HoaWork.resolutionDeadline");
  const router = useRouter();
  const [date, setDate] = useState(deadline ?? "");
  const [text, setText] = useState(source ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (date && text.trim().length < 3) {
      setState("error");
      setMessage(t("sourceRequired"));
      return;
    }
    setState("saving");
    const result = await bff(`/api/bff/hoa/meetings/${meetingId}`, {
      method: "PATCH",
      body: JSON.stringify({
        resolution_deadline_at: date || null,
        resolution_deadline_source: date ? text.trim() : null,
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
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`} aria-labelledby="resolution-deadline-title">
      <h2 id="resolution-deadline-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-sm text-muted">{t("hint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("date")}</span>
        <input
          className={`${ui.input} sm:w-48`}
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          data-testid="resolution-deadline-at"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("source")}</span>
        <input
          className={ui.input}
          type="text"
          maxLength={4000}
          value={text}
          onChange={(e) => setText(e.target.value)}
          data-testid="resolution-deadline-source"
        />
      </label>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={state === "saving"}>
          {t("save")}
        </button>
      </div>
      {state === "saved" ? <p className={ui.success}>{t("saved")}</p> : null}
      {state === "error" && message ? (
        <p role="alert" className={ui.alert}>
          {message}
        </p>
      ) : null}
    </form>
  );
}
