import { getTranslations } from "next-intl/server";

import { CpiAdmin } from "@/components/letting/CpiAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Index values of the consumer price index (AO03): CSV import and release, platform administrators only. */
export default async function IndexValuesPage() {
  const t = await getTranslations("PlatformCpi");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <CpiAdmin />
    </div>
  );
}
