import { getTranslations } from "next-intl/server";

import { LicensingAdmin, type LicTenant } from "@/components/platform/LicensingAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M27-03: licences, price list, billing preview and usage history for platform administrators. */
export default async function PlatformLicensingPage() {
  const t = await getTranslations("PlatformLicensing");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const [tenants, prices] = await Promise.all([serverFetch("/api/v1/platform/tenants"), serverFetch("/api/v1/platform/price-list")]);
  const tenantRows = tenants.ok ? ((await tenants.json()) as LicTenant[]) : [];
  const priceRows = prices.ok ? await prices.json() : [];
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <LicensingAdmin tenants={tenantRows} initialPrices={priceRows} />
    </div>
  );
}
