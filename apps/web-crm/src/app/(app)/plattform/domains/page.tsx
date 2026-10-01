import { getTranslations } from "next-intl/server";

import { TenantDomainsAdmin, type DomTenant } from "@/components/platform/TenantDomainsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** AA17 (GA01): Plattformverwaltung für Administratoren der Plattform. */
export default async function Page() {
  const t = await getTranslations("AA17");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const tenants = await serverFetch("/api/v1/platform/tenants");
  const rows = tenants.ok ? ((await tenants.json()) as DomTenant[]) : [];
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("domains.title")} description={t("domains.intro")} />
      <TenantDomainsAdmin tenants={rows} />
    </div>
  );
}
