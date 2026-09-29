"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

import type { HandoverOffline } from "./useHandoverOffline";

/** Visible state of the offline capture (rule M30-10): connection, number of queued changes,
 *  the replay state, the conflict question and the discarded records after a reload. Shown
 *  only while the tenant switch is on; without it the editor keeps the plain notice. */
export function OfflineBanner({ offline }: { offline: HandoverOffline }) {
  const t = useTranslations("Handover.offline");
  const count = offline.pending.length;
  if (!offline.enabled) return null;
  const show = !offline.online || count > 0 || offline.lost > 0 || offline.failure || offline.syncState !== "idle";
  if (!show) return null;
  return (
    <div role="status" className={`${offline.online && count === 0 && !offline.failure ? ui.notice : ui.warning} flex flex-col gap-2`} data-testid="offline-banner">
      <p className="font-medium">{offline.online ? t("onlineTitle") : t("offlineTitle")}</p>
      {count > 0 ? <p data-testid="offline-pending">{t("pending", { count })}</p> : null}
      {!offline.online ? <p className="text-sm">{t("hint")}</p> : null}
      {offline.lost > 0 ? (
        <p className="text-sm" data-testid="offline-lost">
          {t("lost", { count: offline.lost })}
        </p>
      ) : null}
      {offline.syncState === "running" ? <p className="text-sm">{t("syncing")}</p> : null}
      {offline.failure ? (
        <p role="alert" className="text-sm">
          {t("failed", { message: offline.failure })}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {offline.online && count > 0 && offline.syncState !== "running" && !offline.conflict ? (
          <button type="button" className={ui.buttonSm} onClick={() => void offline.sync()} data-testid="offline-sync">
            {t("syncNow")}
          </button>
        ) : null}
        {count > 0 ? (
          <button type="button" className={ui.buttonSm} onClick={() => void offline.discardAll()} data-testid="offline-discard">
            {t("discard")}
          </button>
        ) : null}
      </div>
    </div>
  );
}
