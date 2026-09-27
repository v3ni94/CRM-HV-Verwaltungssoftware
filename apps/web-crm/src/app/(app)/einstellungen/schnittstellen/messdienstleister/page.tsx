import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MeteringSettings } from "@/components/metering/MeteringSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { type MeteringConnection, type MeteringProvider } from "@/lib/metering";

export const dynamic = "force-dynamic";

/** Einstellungen → Schnittstellen → Messdienstleister (master prompt Messdienstleister,
 *  sections 2, 4 and 6): connections with setup wizard, central assignment overview with bulk
 *  release, CSV import and export. Read needs metering_data:read; the API enforces the manage,
 *  update and sync permissions and the tenant switch metering_module_enabled again. */
export default async function MeteringSettingsPage() {
  const t = await getTranslations("Metering");
  const ts = await getTranslations("Settings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("metering_data:read")) notFound();
  const [providersRes, connectionsRes, settingsRes] = await Promise.all([
    serverFetch("/api/v1/metering/providers"),
    serverFetch("/api/v1/metering/connections"),
    serverFetch("/api/v1/tenant/settings"),
  ]);
  const providers: MeteringProvider[] = providersRes.ok ? ((await providersRes.json()) as MeteringProvider[]) : [];
  const connections: MeteringConnection[] = connectionsRes.ok ? ((await connectionsRes.json()) as MeteringConnection[]) : [];
  const settings = settingsRes.ok ? ((await settingsRes.json()) as { metering_module_enabled?: boolean }) : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[
          { href: "/einstellungen", label: ts("title") },
          { href: "/einstellungen/schnittstellen", label: t("interfaces") },
          { label: t("title") },
        ]}
        title={t("title")}
        description={t("pageIntro")}
      />
      <MeteringSettings
        providers={providers}
        connections={connections}
        loadFailed={!connectionsRes.ok || !providersRes.ok}
        moduleEnabled={settings ? Boolean(settings.metering_module_enabled) : true}
        permissions={permissions}
      />
    </div>
  );
}
