import { getTranslations } from "next-intl/server";

import {
  PlatformOverview,
  type OverviewData,
  type OverviewProperty,
  type OverviewTicket,
} from "@/components/platform/PlatformOverview";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

async function readJson<T>(path: string, fallback: T): Promise<T> {
  const response = await serverFetch(path);
  redirectIfUnauthenticated(response);
  if (!response.ok) return fallback;
  return (await response.json()) as T;
}

/** Cross tenant working view (M2-05): read only figures and lists over the tenants of the
 *  caller's memberships, aggregated server side per tenant (RLS in force). Writing needs the
 *  recorded tenant switch ("Im Mandanten öffnen"). */
export default async function PlatformOverviewPage() {
  const t = await getTranslations("PlatformOverview");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const [overview, tickets, properties] = await Promise.all([
    readJson<OverviewData>("/api/v1/platform/overview", { tenants: [], totals: {} }),
    readJson<OverviewTicket[]>("/api/v1/platform/overview/tickets?limit=50", []),
    readJson<OverviewProperty[]>("/api/v1/platform/overview/properties?limit=100", []),
  ]);
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <PlatformOverview
        currentTenantId={me.data.tenant_id ?? null}
        overview={overview}
        tickets={tickets}
        properties={properties}
      />
    </div>
  );
}
