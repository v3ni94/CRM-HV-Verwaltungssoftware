"use client";

import { useFormatter, useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** Schwarzes Brett (M21-01, A54): current notices of the own properties. Reading a notice
 *  writes nothing; a notice is information of the management, not a delivery. */
export type PortalNotice = {
  id: string;
  property_id: string;
  property_number: string;
  property_name: string;
  title: string;
  body: string;
  valid_from: string;
  valid_to: string | null;
  has_document: boolean;
  is_new: boolean;
  created_at: string;
};

export function NoticeList({ notices }: { notices: PortalNotice[] }) {
  const t = useTranslations("Notices");
  const format = useFormatter();
  const day = (value: string) => format.dateTime(new Date(`${value}T00:00:00`), { day: "2-digit", month: "2-digit", year: "numeric" });
  if (notices.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3" data-testid="notices">
      {notices.map((n) => (
        <li key={n.id} className={`${ui.card} flex flex-col gap-1`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <span className="flex flex-col gap-0.5">
              <span className="font-medium">{n.title}</span>
              <span className="text-xs text-subtle">
                {n.property_number} {n.property_name}
                {" · "}
                {n.valid_to ? t("validUntil", { date: day(n.valid_to) }) : t("validFrom", { date: day(n.valid_from) })}
              </span>
            </span>
            {n.is_new ? <span className={ui.badgeGold}>{t("new")}</span> : null}
          </div>
          <p className="whitespace-pre-wrap text-sm">{n.body}</p>
          {n.has_document ? (
            <a href={`/api/portal-files/portal/notices/${n.id}/document`} className={`${ui.buttonSm} self-start`}>
              {t("download")}
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
