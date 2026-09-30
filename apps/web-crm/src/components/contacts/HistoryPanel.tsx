import { useTranslations } from "next-intl";

import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Kommunikationshistorie des Kontakts (M23): E-Mails, Zustellungen und Tickets in einer
 *  Liste, neueste zuerst. Quelle: GET /contacts/{id}/history; je nach Recht sind einzelne
 *  Arten leer, die Liste ändert nichts. */
export type HistoryEvent = {
  kind: string;
  at: string;
  title: string;
  id: string;
  status: string | null;
};

const KINDS = [
  "email_in",
  "email_out",
  "dispatch_post",
  "dispatch_email",
  "dispatch_portal",
  "dispatch_sms",
  "dispatch_registered",
  "dispatch_courier",
  "ticket",
] as const;

export function HistoryPanel({ events }: { events: HistoryEvent[] }) {
  const t = useTranslations("ContactHistory");
  if (!events.length) return <p className="text-sm text-muted">{t("none")}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {events.map((e) => (
        <li key={`${e.kind}-${e.id}`} className={ui.card}>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className={ui.badge}>
              {(KINDS as readonly string[]).includes(e.kind) ? t(`kind.${e.kind}`) : e.kind}
            </span>
            <span className="text-xs text-muted">{formatDateTime(e.at)}</span>
            {e.status ? (
              <span className="text-xs text-muted">{t("status", { value: e.status })}</span>
            ) : null}
          </div>
          <p className="mt-1 text-sm">{e.title}</p>
        </li>
      ))}
    </ul>
  );
}
