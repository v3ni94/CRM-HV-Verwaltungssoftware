"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CalendarTarget = "internal" | "default" | "own";

export type Attendee = { email: string; name: string };

export type CreateEventInput = {
  title: string;
  starts_on: string;
  all_day: boolean;
  shared: boolean;
  notes: string;
  target: CalendarTarget;
  location: string;
  attendees: Attendee[];
  source_type: "manual" | "ticket" | "handover";
  source_id: string | null;
};

type ContactHit = { id: string; display_name: string; primary_email?: string | null };

/** Create dialog: internal (own workspace, optionally shared) or a Google target (default or
 *  own assigned mailbox), defaulting to "own" when the user has an assigned mailbox with
 *  calendar access, otherwise "default" (M23-02). Location and prospective attendees (picked
 *  from contacts) are stored with the appointment but never sent as a Google invitation from
 *  here (rule M23-05); a separate, explicitly confirmed action does that later. `prefill` locks
 *  the origin link (ticket or handover protocol) and pre-fills the title when opened from
 *  there. */
export function CreateEventDialog({
  defaultTarget,
  hasOwnMailbox,
  hasDefaultMailbox,
  onCreate,
  onClose,
  prefill,
}: {
  defaultTarget: CalendarTarget;
  hasOwnMailbox: boolean;
  hasDefaultMailbox: boolean;
  onCreate: (input: CreateEventInput) => Promise<string | null>;
  onClose: () => void;
  prefill?: {
    title?: string;
    source_type: "ticket" | "handover";
    source_id: string;
    starts_on?: string;
  };
}) {
  const t = useTranslations("Workspace");
  const [title, setTitle] = useState(prefill?.title ?? "");
  const [day, setDay] = useState(prefill?.starts_on ?? "");
  const [allDay, setAllDay] = useState(true);
  const [shared, setShared] = useState(false);
  const [notes, setNotes] = useState("");
  const [location, setLocation] = useState("");
  const [target, setTarget] = useState<CalendarTarget>(defaultTarget);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attendees, setAttendees] = useState<Attendee[]>([]);
  const [contactQuery, setContactQuery] = useState("");
  const [contactHits, setContactHits] = useState<ContactHit[]>([]);

  async function searchContacts() {
    const result = await bff<ContactHit[] | { items?: ContactHit[] }>(
      `/api/bff/contacts?q=${encodeURIComponent(contactQuery)}&page_size=10`,
    );
    if (result.ok) setContactHits(Array.isArray(result.data) ? result.data : (result.data.items ?? []));
  }

  function addAttendee(contact: ContactHit) {
    if (!contact.primary_email) return;
    if (attendees.some((a) => a.email === contact.primary_email)) return;
    setAttendees((prev) => [...prev, { email: contact.primary_email as string, name: contact.display_name }]);
    setContactHits([]);
    setContactQuery("");
  }

  function removeAttendee(email: string) {
    setAttendees((prev) => prev.filter((a) => a.email !== email));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const message = await onCreate({
      title,
      starts_on: day,
      all_day: allDay,
      shared,
      notes,
      target,
      location,
      attendees,
      source_type: prefill?.source_type ?? "manual",
      source_id: prefill?.source_id ?? null,
    });
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
          <span className={ui.label}>{t("location")}</span>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={ui.input} />
        </label>
        {target !== "internal" ? (
          <div className="flex flex-col gap-1.5">
            <span className={ui.label}>{t("attendees")}</span>
            {attendees.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {attendees.map((a) => (
                  <li key={a.email} className={ui.badge}>
                    {a.name || a.email}
                    <button type="button" aria-label={t("removeAttendee", { name: a.name || a.email })} onClick={() => removeAttendee(a.email)}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="flex gap-2">
              <input
                aria-label={t("attendeeSearch")}
                className={ui.input}
                value={contactQuery}
                onChange={(e) => setContactQuery(e.target.value)}
                placeholder={t("attendeeSearchPlaceholder")}
              />
              <button type="button" className={ui.button} onClick={() => void searchContacts()} disabled={contactQuery.length < 2}>
                {t("search")}
              </button>
            </div>
            {contactHits.length ? (
              <ul className="flex flex-wrap gap-1.5">
                {contactHits.map((c) => (
                  <li key={c.id}>
                    <button type="button" className={ui.buttonSm} disabled={!c.primary_email} onClick={() => addAttendee(c)}>
                      + {c.display_name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className={ui.help}>{t("attendeesHint")}</p>
          </div>
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
