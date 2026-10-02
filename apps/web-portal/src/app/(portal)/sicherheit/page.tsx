import { getTranslations } from "next-intl/server";

import { ActiveSessions, PasswordChange } from "@/components/portal/AccountSessions";
import { SecuritySettings } from "@/components/portal/SecuritySettings";
import { SupportConsent } from "@/components/portal/SupportConsent";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Sicherheit (operator 26.09.2026, M2-01): optional second factor and remembered devices of
 *  the own portal account. */
export default async function SecurityPage() {
  const api = serverApi();
  const [t, me, devices, activeSessions] = await Promise.all([
    getTranslations("Security"),
    api.GET("/api/v1/auth/me"),
    api.GET("/api/v1/auth/trusted-devices"),
    api.GET("/api/v1/auth/sessions"),
  ]);
  redirectIfUnauthenticated(me.response);
  // SA-02: the consent card appears only while the tenant has the support view switched on.
  const consentResponse = await serverFetch("/api/v1/portal/support-consent");
  const consent = consentResponse.ok
    ? ((await consentResponse.json()) as { active: boolean; expires_at: string | null; available: boolean })
    : null;
  // S16-01: the passkey card appears only while passkeys are switched on (operator release).
  const passkeysResponse = await serverFetch("/api/v1/auth/webauthn/status");
  const passkeysAvailable = passkeysResponse.ok
    ? ((await passkeysResponse.json()) as { available: boolean }).available === true
    : false;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <p className={ui.notice}>{t("intro")}</p>
      <SecuritySettings
        totpEnabled={me.data?.totp_enabled ?? false}
        initialDevices={devices.data ?? []}
        passkeysAvailable={passkeysAvailable}
        mfaRequired={(me.data as { mfa_required?: boolean } | undefined)?.mfa_required ?? false}
      />
      {/* GAH-305: Passwort ändern und aktive Sitzungen. */}
      <PasswordChange />
      <ActiveSessions initial={activeSessions.data ?? []} />
      {consent?.available ? <SupportConsent initial={consent} /> : null}
    </div>
  );
}
