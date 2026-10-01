import { getTranslations } from "next-intl/server";

import {
  ReleaseGatesAdmin,
  type GateChecklist,
  type GateOverview,
} from "@/components/platform/ReleaseGatesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** GA14-04 (AB02): release gates G1 to G5 per tenant for platform administrators. */
export default async function PlatformReleaseGatesPage() {
  const t = await getTranslations("PlatformGates");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const tenants = (await serverApi().GET("/api/v1/platform/tenants")).data ?? [];
  const activeTenantId = me.data.tenant_id ?? null;
  const first = tenants.find((tn) => tn.id === activeTenantId) ?? tenants[0];
  let initial: GateOverview | null = null;
  if (first) {
    const response = await serverFetch(`/api/v1/platform/tenants/${first.id}/release-gates`);
    if (response.ok) initial = (await response.json()) as GateOverview;
  }
  const lists = await serverFetch("/api/v1/tenant/release-gates/checklists");
  const checklists = lists.ok ? ((await lists.json()) as GateChecklist[]) : [];
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <ReleaseGatesAdmin
        tenants={tenants}
        activeTenantId={activeTenantId}
        initial={initial}
        checklists={checklists}
      />
    </div>
  );
}
