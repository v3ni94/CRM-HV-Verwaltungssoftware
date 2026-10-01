import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { type MfaPolicy, MfaPolicySettings } from "@/components/settings/MfaPolicySettings";
import { PortalRolePermissions } from "@/components/settings/PortalRolePermissions";
import { RolesAdmin } from "@/components/settings/RolesAdmin";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function RolesPage() {
  const t = await getTranslations("Roles");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("roles:read")) notFound();
  const roles = await api.GET("/api/v1/tenant/roles");
  const portalMatrix = can("tenant_settings:read")
    ? await api.GET("/api/v1/tenant/portal-role-permissions")
    : null;
  // M2-04: second factor policy per role (not yet in the generated client).
  const mfaPolicy = can("tenant_settings:read")
    ? await serverFetch("/api/v1/auth/mfa-policy").then(async (r) => (r.ok ? ((await r.json()) as MfaPolicy) : null))
    : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <RolesAdmin initialRoles={roles.data ?? []} canUpdate={can("roles:update")} />
      {portalMatrix?.data ? (
        <PortalRolePermissions
          catalogue={portalMatrix.data.catalogue as string[]}
          initialRoles={portalMatrix.data.roles as Record<string, string[]>}
          canUpdate={can("tenant_settings:update")}
        />
      ) : null}
      {mfaPolicy ? <MfaPolicySettings initial={mfaPolicy} canUpdate={can("tenant_settings:update")} /> : null}
    </div>
  );
}
