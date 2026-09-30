"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PortalFeatures = {
  chat_enabled: boolean;
  chat_ai_prequalification_enabled: boolean;
  support_login_enabled: boolean;
};
export type PortalStatistics = {
  period_days: number;
  accounts: { total: number; invited: number; active: number };
  active_users: number;
  document_retrievals: Record<string, number>;
  form_submissions: number;
  portal_tickets: number;
};

const KEYS: (keyof PortalFeatures)[] = ["chat_enabled", "chat_ai_prequalification_enabled", "support_login_enabled"];

/** Portalfunktionen und Statistik je Mandant (M21-08, SA-01): Schalter sind standardmäßig aus;
 *  die KI-Vorqualifizierung braucht zusätzlich den freigegebenen KI-Anbieter mit AVV, die
 *  Support-Sicht zusätzlich die Einwilligung des Nutzers. Die Statistik zählt nur, sie zeigt
 *  keine personenbezogenen Angaben. */
export function PortalManagement({
  initialFeatures,
  statistics,
  canManage,
}: {
  initialFeatures: PortalFeatures;
  statistics: PortalStatistics | null;
  canManage: boolean;
}) {
  const t = useTranslations("PortalManagement");
  const [features, setFeatures] = useState<PortalFeatures>(initialFeatures);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function toggle(key: keyof PortalFeatures, value: boolean) {
    setBusy(true);
    setError(null);
    const res = await bff<PortalFeatures>("/api/bff/portal-admin/features", {
      method: "PATCH",
      body: JSON.stringify({ [key]: value }),
    });
    setBusy(false);
    if (res.ok) setFeatures(res.data);
    else setError(res.message);
  }

  return (
    <section className="flex flex-col gap-4" aria-labelledby="portal-mgmt-title">
      <h2 id="portal-mgmt-title" className={ui.h2}>
        {t("title")}
      </h2>
      <div className={`${ui.card} flex flex-col gap-2`}>
        <h3 className="text-base font-semibold">{t("features")}</h3>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {KEYS.map((key) => (
          <label key={key} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={features[key]}
              disabled={busy || !canManage || (key === "chat_ai_prequalification_enabled" && !features.chat_enabled)}
              onChange={(e) => toggle(key, e.target.checked)}
            />
            <span className="flex flex-col">
              <span>{t(`keys.${key}`)}</span>
              <span className={ui.help}>{t(`help.${key}`)}</span>
            </span>
          </label>
        ))}
      </div>
      {statistics ? (
        <div className={`${ui.card} flex flex-col gap-1 text-sm`} data-testid="portal-statistics">
          <h3 className="text-base font-semibold">{t("statistics", { days: statistics.period_days })}</h3>
          <span>{t("accountsTotal", { count: statistics.accounts.total })}</span>
          <span>{t("accountsInvited", { count: statistics.accounts.invited })}</span>
          <span>{t("accountsActive", { count: statistics.accounts.active })}</span>
          <span>{t("activeUsers", { count: statistics.active_users })}</span>
          <span>
            {t("retrievals", {
              opened: statistics.document_retrievals.opened ?? 0,
              downloaded: statistics.document_retrievals.downloaded ?? 0,
            })}
          </span>
          <span>{t("submissions", { count: statistics.form_submissions })}</span>
          <span>{t("tickets", { count: statistics.portal_tickets })}</span>
        </div>
      ) : null}
    </section>
  );
}
