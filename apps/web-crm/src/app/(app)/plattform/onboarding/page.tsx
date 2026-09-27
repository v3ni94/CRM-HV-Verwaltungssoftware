import { getTranslations } from "next-intl/server";

import { OnboardingWizard, TenantExport } from "@/components/platform/OnboardingWizard";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M27-03: onboarding wizard for third party tenants and tenant export (four eyes). */
export default async function PlatformOnboardingPage() {
  const t = await getTranslations("PlatformOnboarding");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const tenants = (await serverApi().GET("/api/v1/platform/tenants")).data ?? [];
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <OnboardingWizard />
      <TenantExport tenants={tenants} />
    </div>
  );
}
