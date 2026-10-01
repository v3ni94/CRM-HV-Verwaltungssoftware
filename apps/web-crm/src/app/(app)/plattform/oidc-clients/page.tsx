import { getTranslations } from "next-intl/server";

import { OidcClientsAdmin } from "@/components/platform/OidcClientsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** AA17 (GA01): Plattformverwaltung für Administratoren der Plattform. */
export default async function Page() {
  const t = await getTranslations("AA17");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;

  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("oidc.title")} description={t("oidc.intro")} />
      <OidcClientsAdmin />
    </div>
  );
}
