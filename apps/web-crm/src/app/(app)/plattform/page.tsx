import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { DemoFlagToggle } from "@/components/platform/DemoFlagToggle";
import { TenantAdmin } from "@/components/platform/TenantAdmin";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusChip } from "@/components/ui/StatusChip";

export const dynamic = "force-dynamic";

type Readiness = {
  checklist: { item: string; done: boolean }[];
  usage: { units: number; users: number; unit_quota: number };
  gates: Record<string, boolean>;
  g5_evidence: { item: string; done: boolean }[];
  demo?: boolean;
};

/** Platform view (M27): read only. Prices and licences are maintained via the API by platform
 *  administrators; the page never opens a gate. */
export default async function PlatformPage() {
  const t = await getTranslations("Platform");
  const tl = await getTranslations("PlatformLicensing");
  const tx = await getTranslations("AA17");
  const tg = await getTranslations("PlatformGates");
  const ta = await getTranslations("AC02");
  const tb = await getTranslations("AD10");
  const tae = await getTranslations("AE01");
  const tdemo = await getTranslations("AE36");
  const api = serverApi();
  const me = await getMe();
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
      <nav className="flex flex-wrap gap-4 text-sm">
        <Link className="underline" href="/plattform/mietrecht">
          {t("rentLaw")}
        </Link>
        <Link className="underline" href="/plattform/preisliste">
          {t("pricingLink")}
        </Link>
        <Link className="underline" href="/plattform/lizenzen">
          {tl("link")}
        </Link>
        <Link className="underline" href="/plattform/freigabe-g5">
          {t("g5Link")}
        </Link>
        <Link className="underline" href="/plattform/freigabestufen">
          {tg("link")}
        </Link>
        <Link className="underline" href="/plattform/domains">
          {tx("domainsLink")}
        </Link>
        <Link className="underline" href="/plattform/oidc-clients">
          {tx("oidcLink")}
        </Link>
        <Link className="underline" href="/plattform/audit">
          {ta("link")}
        </Link>
        <Link className="underline" href="/plattform/abnahme">
          {tae("link")}
        </Link>
        <Link className="underline" href="/plattform/betrieb">
          {tb("link")}
        </Link>
        <Link className="underline" href="/plattform/onboarding">
          {t("onboardingLink")}
        </Link>
      </nav>
      <TenantAdmin initialTenants={tenants.data ?? []} />
      {rows.map(({ tenant, readiness }) => (
        <section key={tenant.id} className={ui.card}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className={ui.h2}>
              {tenant.name}{" "}
              {readiness?.demo ? (
                <span className={ui.badgeGold} title={tdemo("demoHint")}>
                  {tdemo("demoBadge")}
                </span>
              ) : null}
            </h2>
            <DemoFlagToggle tenantId={tenant.id} isDemo={Boolean(readiness?.demo)} />
          </div>
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
                    <li key={g} className="flex items-center gap-2">
                      <span>{g}</span>
                      <StatusChip domain="gate" status={open ? "open" : "closed"} />
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
