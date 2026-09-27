import { getTranslations } from "next-intl/server";

import { G5Evidence, type EvidenceList } from "@/components/platform/G5Evidence";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** M27-02: G5 evidence list per tenant. The page never opens the gate. */
export default async function PlatformG5Page() {
  const t = await getTranslations("PlatformG5");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const tenants = (await serverApi().GET("/api/v1/platform/tenants")).data ?? [];
  let initial: EvidenceList | null = null;
  if (tenants[0]) {
    const response = await serverFetch(`/api/v1/platform/tenants/${tenants[0].id}/g5-evidence`);
    if (response.ok) initial = (await response.json()) as EvidenceList;
  }
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <G5Evidence tenants={tenants} initial={initial} />
    </div>
  );
}
