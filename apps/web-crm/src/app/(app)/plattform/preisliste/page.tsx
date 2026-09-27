import { getTranslations } from "next-intl/server";

import { PricingAdmin, type Pricing } from "@/components/platform/PricingAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M27-01: pricing structure without invented amounts; offer as PDF draft. */
export default async function PlatformPricingPage() {
  const t = await getTranslations("PlatformPricing");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const response = await serverFetch("/api/v1/platform/pricing");
  const pricing = response.ok
    ? ((await response.json()) as Pricing)
    : { items: [], complete: false, missing_amounts: [] };
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <PricingAdmin initial={pricing} />
    </div>
  );
}
