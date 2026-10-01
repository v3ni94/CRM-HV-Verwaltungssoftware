"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { AssistantLogPanel } from "@/components/settings/AssistantLogPanel";
import { ProviderRatingsPanel } from "@/components/settings/ProviderRatingsPanel";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PortalFeatures = {
  chat_enabled: boolean;
  chat_ai_prequalification_enabled: boolean;
  support_login_enabled: boolean;
  owner_rental_income_enabled?: boolean;
  /** AE28 (M7-06, SA-04): Assistent für die eigenen Unterlagen und Datenschutz-Feature, beide aus. */
  chat_bot_enabled?: boolean;
  privacy_feature_enabled?: boolean;
  owner_ticket_scope?: "none" | "released" | "property";
  /** AA14-02: Bewertungen der Dienstleister, off (Standard) oder staff (nur Verwaltung). */
  provider_rating_display?: "off" | "staff";
};
export type PortalStatistics = {
  period_days: number;
  accounts: { total: number; invited: number; active: number };
  active_users: number;
  document_retrievals: Record<string, number>;
  form_submissions: number;
  portal_tickets: number;
};

type BoolKey =
  | "chat_enabled"
  | "chat_ai_prequalification_enabled"
  | "support_login_enabled"
  | "owner_rental_income_enabled"
  | "chat_bot_enabled"
  | "privacy_feature_enabled";
const KEYS: BoolKey[] = [
  "chat_enabled",
  "chat_ai_prequalification_enabled",
  "support_login_enabled",
  "owner_rental_income_enabled",
  "chat_bot_enabled",
  "privacy_feature_enabled",
];
const SCOPES = ["none", "released", "property"] as const;
const RATING_MODES = ["off", "staff"] as const;

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

  async function toggle(key: keyof PortalFeatures, value: boolean | string) {
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
              checked={Boolean(features[key])}
              disabled={busy || !canManage || (key === "chat_ai_prequalification_enabled" && !features.chat_enabled)}
              onChange={(e) => toggle(key, e.target.checked)}
            />
            <span className="flex flex-col">
              <span>{t(`keys.${key}`)}</span>
              <span className={ui.help}>{t(`help.${key}`)}</span>
            </span>
          </label>
        ))}
        <label className="flex flex-col gap-1 text-sm">
          <span>{t("ticketScope")}</span>
          <select
            className={ui.input}
            value={features.owner_ticket_scope ?? "released"}
            disabled={busy || !canManage}
            onChange={(e) => toggle("owner_ticket_scope", e.target.value)}
          >
            {SCOPES.map((s) => (
              <option key={s} value={s}>
                {t(`ticketScopes.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span>{t("ratingDisplay")}</span>
          <select
            className={ui.input}
            value={features.provider_rating_display ?? "off"}
            disabled={busy || !canManage}
            onChange={(e) => toggle("provider_rating_display", e.target.value)}
          >
            {RATING_MODES.map((m) => (
              <option key={m} value={m}>
                {t(`ratingModes.${m}`)}
              </option>
            ))}
          </select>
          <span className={ui.help}>{t("ratingHelp")}</span>
        </label>
      </div>
      {features.provider_rating_display === "staff" ? <ProviderRatingsPanel /> : null}
      {features.chat_bot_enabled && canManage ? <AssistantLogPanel /> : null}
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
