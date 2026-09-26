import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TelephonySettings, type TelephonySettingsOut } from "@/components/settings/TelephonySettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Telefonie (13.5, A70): Webhook-Geheimnis je Mandant setzen (nie anzeigen), Anbieter frei
 *  benennen. Lesen mit tenant_settings:read, Speichern mit tenant_settings:update. */
export default async function TelephonySettingsPage() {
  const t = await getTranslations("TelephonySettings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const res = await serverFetch("/api/v1/communication/telephony/settings");
  const initial: TelephonySettingsOut = res.ok
    ? ((await res.json()) as TelephonySettingsOut)
    : { enabled: false, provider_label: null, has_webhook_secret: false, webhook_path: "/api/v1/communication/webhooks/telephony" };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("pageIntro")} />
      <TelephonySettings initial={initial} canManage={permissions.includes("tenant_settings:update")} />
    </div>
  );
}
