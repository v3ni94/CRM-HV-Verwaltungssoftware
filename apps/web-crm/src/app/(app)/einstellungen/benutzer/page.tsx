import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MembersAdmin, type LegalEntityOption } from "@/components/settings/MembersAdmin";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Query parameters `email` and `role` prefill the invitation form (used by the objektakte
 * user mapping report, M35 Stufe 4); nothing is created without the administrator submitting. */
export default async function MembersPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [t, query] = await Promise.all([getTranslations("Members"), searchParams]);
  const first = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("members:read")) notFound();
  const [members, roles, competenceCatalogue, legalEntities] = await Promise.all([
    api.GET("/api/v1/tenant/members"),
    api.GET("/api/v1/tenant/roles"),
    api.GET("/api/v1/tenant/competence-catalogue"),
    // Zugriffsbereich je Rechtsträger für Steuerberater (A37); Liste ist nur eine Auswahlhilfe.
    serverFetch("/api/v1/tenant/legal-entities").then(async (r) => (r.ok ? ((await r.json()) as LegalEntityOption[]) : [])),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("neverDeleted")}</p>
      <MembersAdmin
        initialMembers={members.data ?? []}
        roles={roles.data ?? []}
        competenceCatalogue={(competenceCatalogue.data ?? []) as { code: string; label: string }[]}
        legalEntityOptions={legalEntities}
        canCreate={can("members:create")}
        canUpdate={can("members:update")}
        canUpdateScope={can("tenant_settings:update")}
        prefill={{ email: first(query.email), roleCodes: first(query.role) ? [first(query.role)] : [] }}
      />
    </div>
  );
}
