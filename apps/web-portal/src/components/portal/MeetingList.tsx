"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { PortalMeeting } from "@/components/portal/types";
import { ui } from "@/lib/ui";

const KNOWN_MODE = new Set(["presence", "hybrid", "virtual"]);
const KNOWN_STATUS = new Set(["invited", "held", "closed"]);

/** Versammlungen der eigenen Gemeinschaft (M25-03, V13): Einwahldaten erscheinen nur, wenn
 *  die API sie liefert (hybride oder virtuelle Form, nach Einladung, nur Eigentümer). */
export function MeetingList({ rows }: { rows: PortalMeeting[] }) {
  const t = useTranslations("Meetings");
  const format = useFormatter();
  if (rows.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.id} className={`${ui.card} flex flex-col gap-2`} data-testid="portal-meeting">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium break-words">
              {format.dateTime(new Date(row.scheduled_at), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
              {row.legal_entity_name ? ` · ${row.legal_entity_name}` : ""}
            </span>
            <span className={ui.badge}>{KNOWN_MODE.has(row.mode) ? t(`mode.${row.mode}`) : row.mode_label}</span>
          </div>
          <p className="text-xs text-subtle">
            {KNOWN_STATUS.has(row.status) ? t(`status.${row.status}`) : row.status}
            {row.location ? ` · ${row.location}` : ""}
          </p>
          {row.notice ? <p className="text-sm text-fg whitespace-pre-line">{row.notice}</p> : null}
          {row.dial_in_url || row.dial_in_access ? (
            <div className="flex flex-col gap-1 rounded-md border border-border p-3" data-testid="dial-in">
              <span className={ui.label}>{t("dialIn")}</span>
              {row.dial_in_url ? (
                <a className="text-sm underline break-all" href={row.dial_in_url} rel="noreferrer" target="_blank">
                  {row.dial_in_url}
                </a>
              ) : null}
              {row.dial_in_access ? <p className="text-sm whitespace-pre-line break-words">{row.dial_in_access}</p> : null}
              {row.dial_in_note ? <p className="text-xs text-subtle">{row.dial_in_note}</p> : null}
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
