"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Schwarzes Brett (M21-01, A54): current notices of the own properties. Reading a notice
 *  writes nothing; a notice is information of the management, not a delivery. */
export type NoticeLevel = "neutral" | "info" | "warning" | "danger";

export type PortalNotice = {
  id: string;
  property_id: string;
  property_number: string;
  property_name: string;
  title: string;
  body: string;
  valid_from: string;
  valid_to: string | null;
  category?: string | null;
  type?: NoticeLevel;
  has_document: boolean;
  documents?: { id: string; filename: string }[];
  is_new: boolean;
  /** Read confirmation of the own account (indication only, no delivery). */
  read?: boolean;
  read_at?: string | null;
  created_at: string;
};

const LEVEL_BADGE: Record<NoticeLevel, string> = {
  neutral: ui.badge,
  info: ui.badgeInfo,
  warning: ui.badgeWarning,
  danger: ui.badgeDanger,
};
const LEVEL_FRAME: Record<NoticeLevel, string> = {
  neutral: "",
  info: " border-l-4 border-l-info-fg",
  warning: " border-l-4 border-l-warning-fg",
  danger: " border-l-4 border-l-danger-fg",
};

export function NoticeList({ notices }: { notices: PortalNotice[] }) {
  const t = useTranslations("Notices");
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function confirm(id: string) {
    setBusy(id);
    setError(null);
    const res = await bff(`/api/bff/portal/notices/${id}/read`, { method: "POST", body: "{}" });
    setBusy(null);
    if (!res.ok) return setError(res.message);
    setConfirmed((prev) => new Set(prev).add(id));
  }

  const format = useFormatter();
  const day = (value: string) => format.dateTime(new Date(`${value}T00:00:00`), { day: "2-digit", month: "2-digit", year: "numeric" });
  if (notices.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    <ul className="flex flex-col gap-3" data-testid="notices">
      {notices.map((n) => (
        <li key={n.id} className={`${ui.card} flex flex-col gap-1${LEVEL_FRAME[n.type ?? "neutral"]}`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <span className="flex flex-col gap-0.5">
              <span className="font-medium break-words">{n.title}</span>
              <span className="text-xs text-subtle">
                {n.property_number} {n.property_name}
                {" · "}
                {n.valid_to ? t("validUntil", { date: day(n.valid_to) }) : t("validFrom", { date: day(n.valid_from) })}
              </span>
            </span>
            <span className="flex flex-wrap gap-1">
              {n.type && n.type !== "neutral" ? <span className={LEVEL_BADGE[n.type]}>{t(`levels.${n.type}`)}</span> : null}
              {n.is_new ? <span className={ui.badgeGold}>{t("new")}</span> : null}
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm">{n.body}</p>
          {n.documents && n.documents.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {n.documents.map((d) => (
                <a key={d.id} href={`/api/portal-files/portal/notices/${n.id}/documents/${d.id}`} className={`${ui.buttonSm} self-start`}>
                  {t("downloadNamed", { name: d.filename })}
                </a>
              ))}
            </div>
          ) : n.has_document ? (
            <a href={`/api/portal-files/portal/notices/${n.id}/document`} className={`${ui.buttonSm} self-start`}>
              {t("download")}
            </a>
          ) : null}
          {n.read === undefined ? null : n.read || confirmed.has(n.id) ? (
            <span className="text-xs text-subtle">{t("readDone")}</span>
          ) : (
            <button type="button" className={`${ui.buttonSm} self-start`} disabled={busy === n.id} onClick={() => void confirm(n.id)}>
              {t("confirmRead")}
            </button>
          )}
        </li>
      ))}
    </ul>
    </>
  );
}
