"use client";

import { useTranslations } from "next-intl";

import { AppointmentButton } from "@/components/appointments/AppointmentButton";
import { ui } from "@/lib/ui";

/** "Termin anlegen" on the handover protocol detail page: opens the same create dialog as the
 *  calendar page and the ticket detail page, prefilled with the protocol as origin link
 *  (`source_type: "handover"`) and the protocol's date as the default start when the protocol
 *  already carries one. */
export function HandoverAppointmentButton({
  protocolId,
  address,
  handoverDate,
}: {
  protocolId: string;
  address: string | null;
  handoverDate: string | null;
}) {
  const t = useTranslations("Handover");
  return (
    <AppointmentButton
      sourceType="handover"
      sourceId={protocolId}
      title={`${t("appointmentTitle")}${address ? ` ${address}` : ""}`}
      label={t("createAppointment")}
      defaultDate={handoverDate}
      buttonClassName={ui.buttonSm}
    />
  );
}
