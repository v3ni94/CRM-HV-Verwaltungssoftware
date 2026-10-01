import { getTranslations } from "next-intl/server";

import { PlatformAuditList } from "@/components/platform/PlatformAuditList";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** AC02: Plattformaudit für Administratoren der Plattform. */
export default async function Page() {
  const t = await getTranslations("AC02");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} description={t("intro")} />
      <PlatformAuditList />
    </div>
  );
}
