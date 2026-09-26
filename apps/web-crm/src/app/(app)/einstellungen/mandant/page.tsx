import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CompanySettings } from "@/components/settings/CompanySettings";
import { BillingSettingsForm, type BillingSettings } from "@/components/settings/BillingSettings";
import { ManagerEntitySetup, type ManagerEntityStatus } from "@/components/settings/ManagerEntitySetup";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

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
  const billingRes = await serverFetch("/api/v1/tenant/billing-settings");
  const billingData: BillingSettings | null = billingRes.ok ? await billingRes.json() : null;
  const tb = await getTranslations("BillingSettings");
  const managerRes = await serverFetch("/api/v1/tenant/manager-entity");
  const managerData: ManagerEntityStatus | null = managerRes.ok ? await managerRes.json() : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <CompanySettings initial={settings.data.company} branding={settings.data.branding} canUpdate={can("tenant_settings:update")} />
      <ManagerEntitySetup initial={managerData} canUpdate={can("tenant_settings:update")} />
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{tb("title")}</h2>
        {billingData ? (
          <BillingSettingsForm initial={billingData} canUpdate={can("tenant_settings:update")} />
        ) : (
          <p role="alert" className={ui.alert}>{tb("loadError")}</p>
        )}
      </section>
    </div>
  );
}
