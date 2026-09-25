"use client";

import { useTranslations } from "next-intl";

import { AppointmentButton } from "@/components/appointments/AppointmentButton";

/** "Termin anlegen" on the ticket detail page (Ortstermin/Telefontermin, M23-02): thin wrapper
 *  around the generalised {@link AppointmentButton} that fixes the origin link to this ticket
 *  and prefixes the title the same way as before. */
export function TicketAppointmentButton({ ticketId, ticketTitle }: { ticketId: string; ticketTitle: string }) {
  const t = useTranslations("Tickets");
  return (
    <AppointmentButton
      sourceType="ticket"
      sourceId={ticketId}
      title={`${t("createAppointment")}: ${ticketTitle}`}
      label={t("createAppointment")}
    />
  );
}
