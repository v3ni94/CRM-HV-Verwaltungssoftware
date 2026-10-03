"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Dependent = { type: string; id: string; label: string; status: string; applied: boolean; contested: boolean };
type Dependents = { resolution_id: string; status: string; contested: boolean; items: Dependent[] };
type Deadline = { id: string; due_on: string; due_computed: boolean; verify: boolean };

/** Folgen eines Beschlusses (AN19-CRM, GAK-204): `GET /hoa/resolutions/{id}/dependents` zeigt abhängige
 *  Wirtschaftspläne, Sonderumlagen und Abrechnungen mit dem Kennzeichen "angefochten";
 *  `POST /hoa/resolutions/{id}/review-deadline` legt ein Prüfdatum als Frist an. Es wird nichts storniert. */
export function ResolutionFollowUps({ resolutionId }: { resolutionId: string }) {
  const t = useTranslations("Ao05.followUps");
  const [data, setData] = useState<Dependents | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dueOn, setDueOn] = useState("");
  const [note, setNote] = useState("");
  const [created, setCreated] = useState<Deadline | null>(null);
  const load = useBusy();
  const save = useBusy();
  const base = `/api/bff/hoa/resolutions/${resolutionId}`;

  const loadDependents = load.guard(async () => {
    setError(null);
    const res = await bff<Dependents>(`${base}/dependents`);
    if (res.ok) setData(res.data);
    else setError(res.message);
  });
  const setDeadline = save.guard(async (_e?: React.FormEvent) => {
    setError(null);
    setCreated(null);
    const res = await bff<Deadline>(`${base}/review-deadline`, {
      method: "POST",
      body: JSON.stringify({ due_on: dueOn || null, note: note.trim() || null }),
    });
    if (res.ok) setCreated(res.data);
    else setError(res.message);
  });

  return (
    <div className="mt-1 flex flex-col gap-1" data-testid="resolution-followups">
      <div>
        <button type="button" className={ui.buttonSm} disabled={load.busy} onClick={() => void loadDependents()}>
          {t("load")}
        </button>
      </div>
      {data ? (
        <div data-testid="followups-list">
          {data.contested ? <p className={ui.notice}>{t("contestedHint")}</p> : null}
          {data.items.length === 0 ? (
            <p className="text-xs text-muted">{t("none")}</p>
          ) : (
            <ul className="text-xs">
              {data.items.map((d) => (
                <li key={`${d.type}-${d.id}`} data-testid="followup-item">
                  {t(`types.${d.type}`)}: {d.label} ({d.status}){d.applied ? `, ${t("applied")}` : ""}
                  {d.contested ? <strong className="ml-1 text-danger-fg">{t("contested")}</strong> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      <form className="flex flex-col gap-1" onSubmit={(e) => void setDeadline(e)}>
        <label className={ui.label}>
          {t("dueOn")}
          <input type="date" className={ui.input} value={dueOn} onChange={(e) => setDueOn(e.target.value)} />
        </label>
        <label className={ui.label}>
          {t("note")}
          <input className={ui.input} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <p className={ui.help}>{t("deadlineHelp")}</p>
        <div>
          <button type="submit" className={ui.buttonSm} disabled={save.busy}>
            {t("setDeadline")}
          </button>
        </div>
      </form>
      {created ? (
        <p role="status" className={ui.success} data-testid="deadline-created">
          {t("created", { date: formatDate(created.due_on) })}
        </p>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
