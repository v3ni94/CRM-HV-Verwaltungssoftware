"use client";

import { useEffect, useState } from "react";

import type { Attendee, CreateEventInput } from "@/components/calendar/CreateEventDialog";
import { CreateEventDialog } from "@/components/calendar/CreateEventDialog";
import type { CalendarNotice } from "@/components/workspace/CalendarView";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "Termin anlegen" (M23-02, extended for handover protocols): opens the calendar create
 *  dialog, prefilled with the origin link (`source_type`/`source_id`), so the appointment shows
 *  up on /kalender tied back to the ticket or handover protocol it was created from. Additive
 *  only: this component and its one button/dialog are the only change to the host page. */
export function AppointmentButton({
  sourceType,
  sourceId,
  title,
  label,
  defaultDate,
  buttonClassName,
  location,
  attendees,
  createdLinkLabel,
}: {
  sourceType: "ticket" | "handover";
  sourceId: string;
  title: string;
  /** Button label; callers pass their own translated text (e.g. Tickets.createAppointment,
   *  Handover.createAppointment) so this component stays namespace agnostic. */
  label: string;
  defaultDate?: string | null;
  /** Button style; defaults to the regular button used on the ticket detail page. */
  buttonClassName?: string;
  /** Prefilled location and prospective attendees (stored as draft only, rule M23-05). */
  location?: string | null;
  attendees?: Attendee[];
  /** When given, a link to the created appointment on /kalender is shown after creating;
   *  receives the appointment date formatted as TT.MM.JJJJ. */
  createdLinkLabel?: (date: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const [notices, setNotices] = useState<CalendarNotice[]>([]);

  useEffect(() => {
    if (!open) return;
    const day = todayIso();
    void bff<{ notices: CalendarNotice[] }>(`/api/bff/workspace/calendar?start=${day}&end=${day}`).then((result) => {
      if (result.ok) setNotices(result.data.notices);
    });
  }, [open]);

  const hasDefaultMailbox = notices.some((n) => n.source === "default" && n.connected);
  const hasOwnMailbox = notices.some((n) => n.source === "own" && n.connected);

  async function create(input: CreateEventInput): Promise<string | null> {
    const body: Record<string, unknown> = {
      title: input.title,
      starts_on: input.starts_on,
      all_day: input.all_day,
      target: input.target === "internal" ? "default" : input.target,
      notes: input.notes || null,
      location: input.location || null,
      attendees: input.attendees,
      source_type: sourceType,
      source_id: sourceId,
    };
    const result = await bff<{ date?: string }>("/api/bff/workspace/calendar", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (!result.ok) return result.message;
    setCreated(result.data?.date ?? input.starts_on);
    return null;
  }

  return (
    <>
      <button type="button" className={buttonClassName ?? ui.button} onClick={() => setOpen(true)}>
        {label}
      </button>
      {created && createdLinkLabel ? (
        <a className={ui.buttonSm} href={`/kalender?datum=${encodeURIComponent(created)}`}>
          {createdLinkLabel(created.split("-").reverse().join("."))}
        </a>
      ) : null}
      {open ? (
        <CreateEventDialog
          defaultTarget={hasOwnMailbox ? "own" : "default"}
          hasOwnMailbox={hasOwnMailbox}
          hasDefaultMailbox={hasDefaultMailbox}
          onCreate={create}
          onClose={() => setOpen(false)}
          prefill={{
            title,
            source_type: sourceType,
            source_id: sourceId,
            starts_on: defaultDate ?? undefined,
            location: location ?? undefined,
            attendees,
          }}
        />
      ) : null}
    </>
  );
}
