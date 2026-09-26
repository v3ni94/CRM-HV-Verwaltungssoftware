"use client";

import { useTranslations } from "next-intl";

import { AppointmentButton } from "@/components/appointments/AppointmentButton";
import type { Attendee } from "@/components/calendar/CreateEventDialog";
import { ui } from "@/lib/ui";

import type { Item } from "./types";

function text(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/** Participants with an e-mail address as prospective attendees (draft only, rule M23-05). */
export function participantAttendees(participants: Item[]): Attendee[] {
  const seen = new Set<string>();
  const out: Attendee[] = [];
  for (const item of participants) {
    const email = text(item.email);
    if (!email || seen.has(email.toLowerCase())) continue;
    seen.add(email.toLowerCase());
    const name = [text(item.first_name), text(item.last_name)].filter(Boolean).join(" ") || text(item.company);
    out.push({ email, name: name || email });
  }
  return out;
}

/** "Termin anlegen" on the handover protocol detail page: opens the same create dialog as the
 *  calendar page and the ticket detail page, prefilled with the protocol as origin link
 *  (`source_type: "handover"`), title "Übergabe {Objekt/Einheit}", the object address as
 *  location, the participants with e-mail as prospective attendees and the protocol's date as
 *  default start. After creating, a link to the appointment on /kalender is shown. */
export function HandoverAppointmentButton({
  protocolId,
  address,
  handoverDate,
  objectLabel = null,
  unitLabel = null,
  participants = [],
}: {
  protocolId: string;
  address: string | null;
  handoverDate: string | null;
  objectLabel?: string | null;
  unitLabel?: string | null;
  participants?: Item[];
}) {
  const t = useTranslations("Handover");
  const subject = [objectLabel || address, unitLabel].filter(Boolean).join(", ");
  return (
    <AppointmentButton
      sourceType="handover"
      sourceId={protocolId}
      title={`${t("appointmentTitle")}${subject ? ` ${subject}` : ""}`}
      label={t("createAppointment")}
      defaultDate={handoverDate}
      buttonClassName={ui.buttonSm}
      location={address}
      attendees={participantAttendees(participants)}
      createdLinkLabel={(date) => t("appointmentCreatedLink", { date })}
    />
  );
}
