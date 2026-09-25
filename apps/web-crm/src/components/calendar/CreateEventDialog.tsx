"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

export type CalendarTarget = "internal" | "default" | "own";

export type CreateEventInput = {
  title: string;
  starts_on: string;
  all_day: boolean;
  shared: boolean;
  notes: string;
  target: CalendarTarget;
};

/** Create dialog: internal (own workspace, optionally shared) or a Google target (default or
 *  own assigned mailbox), defaulting to "own" when the user has an assigned mailbox with
 *  calendar access, otherwise "default" (M23-02). */
export function CreateEventDialog({
  defaultTarget,
  hasOwnMailbox,
  hasDefaultMailbox,
  onCreate,
  onClose,
}: {
  defaultTarget: CalendarTarget;
  hasOwnMailbox: boolean;
  hasDefaultMailbox: boolean;
  onCreate: (input: CreateEventInput) => Promise<string | null>;
  onClose: () => void;
}) {
  const t = useTranslations("Workspace");
  const [title, setTitle] = useState("");
  const [day, setDay] = useState("");
  const [allDay, setAllDay] = useState(true);
  const [shared, setShared] = useState(false);
  const [notes, setNotes] = useState("");
  const [target, setTarget] = useState<CalendarTarget>(defaultTarget);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const message = await onCreate({ title, starts_on: day, all_day: allDay, shared, notes, target });
    setBusy(false);
    if (message) setError(message);
    else onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-fg/40 p-4" role="dialog" aria-modal="true" aria-label={t("addEntry")}>
      <form onSubmit={submit} className={`${ui.card} flex w-full max-w-md flex-col gap-3`}>
        <h2 className="text-sm font-semibold">{t("addEntry")}</h2>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entryTitle")}</span>
          <input required value={title} onChange={(e) => setTitle(e.target.value)} className={ui.input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("entryDate")}</span>
          <input type="date" required value={day} onChange={(e) => setDay(e.target.value)} className={ui.input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("calendarTarget")}</span>
          <select value={target} onChange={(e) => setTarget(e.target.value as CalendarTarget)} className={ui.input}>
            <option value="internal">{t("calendarSource.internal")}</option>
            <option value="default" disabled={!hasDefaultMailbox}>
              {t("calendarSource.default")}
              {hasDefaultMailbox ? "" : ` (${t("calendarNotConnected")})`}
            </option>
            <option value="own" disabled={!hasOwnMailbox}>
              {t("calendarSource.own")}
              {hasOwnMailbox ? "" : ` (${t("calendarNotConnected")})`}
            </option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} />
          {t("allDay")}
        </label>
        {target === "internal" ? (
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={shared} onChange={(e) => setShared(e.target.checked)} />
            {t("shared")}
          </label>
        ) : null}
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("notes")}</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className={ui.input} rows={3} />
        </label>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <div className={ui.formActions}>
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={onClose}>
            {t("cancel")}
          </button>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {t("addEntry")}
          </button>
        </div>
      </form>
    </div>
  );
}
