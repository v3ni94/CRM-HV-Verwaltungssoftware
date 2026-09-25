import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { TenantAdmin } from "@/components/platform/TenantAdmin";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

type Readiness = {
  checklist: { item: string; done: boolean }[];
  usage: { units: number; users: number; unit_quota: number };
  gates: Record<string, boolean>;
  g5_evidence: { item: string; done: boolean }[];
};

/** Platform view (M27): read only. Prices and licences are maintained via the API by platform
 *  administrators; the page never opens a gate. */
export default async function PlatformPage() {
  const t = await getTranslations("Platform");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  const tenants = await api.GET("/api/v1/platform/tenants");
  const rows = await Promise.all(
    (tenants.data ?? []).map(async (tn) => {
      const r = await api.GET("/api/v1/platform/tenants/{tenant_id}/readiness", {
        params: { path: { tenant_id: tn.id } },
      });
      return { tenant: tn, readiness: (r.data ?? null) as Readiness | null };
    }),
  );
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("notice")}</p>
      <Link className="text-sm underline" href="/plattform/mietrecht">
        {t("rentLaw")}
      </Link>
      <TenantAdmin initialTenants={tenants.data ?? []} />
      {rows.map(({ tenant, readiness }) => (
        <section key={tenant.id} className={ui.card}>
          <h2 className={ui.h2}>{tenant.name}</h2>
          {readiness ? (
            <div className="mt-2 grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <h3 className="text-xs text-muted">{t("usage")}</h3>
                <p>{t("usageLine", readiness.usage)}</p>
                <ul>
                  {readiness.checklist.map((c) => (
                    <li key={c.item}>
                      {c.done ? "✓" : "○"} {c.item}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xs text-muted">{t("gates")}</h3>
                <ul>
                  {Object.entries(readiness.gates).map(([g, open]) => (
                    <li key={g}>
                      {g}: {open ? t("open") : t("closed")}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-xs text-muted">{t("g5")}</h3>
                <ul>
                  {readiness.g5_evidence.map((e) => (
                    <li key={e.item}>
                      {e.done ? "✓" : "○"} {e.item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("noData")}</p>
          )}
        </section>
      ))}
    </div>
  );
}
