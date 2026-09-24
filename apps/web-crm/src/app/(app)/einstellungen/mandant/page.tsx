import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CompanySettings } from "@/components/settings/CompanySettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function CompanySettingsPage() {
  const t = await getTranslations("CompanySettings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("tenant_settings:read")) notFound();
  const settings = await api.GET("/api/v1/tenant/settings");
  if (!settings.data) return <p role="alert" className={ui.alert}>{t("loadError")}</p>;
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      <CompanySettings initial={settings.data.company} branding={settings.data.branding} canUpdate={can("tenant_settings:update")} />
    </div>
  );
}
