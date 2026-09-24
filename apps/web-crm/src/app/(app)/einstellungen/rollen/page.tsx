import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { RolesAdmin } from "@/components/settings/RolesAdmin";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function RolesPage() {
  const t = await getTranslations("Roles");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("roles:read")) notFound();
  const roles = await api.GET("/api/v1/tenant/roles");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <RolesAdmin initialRoles={roles.data ?? []} canUpdate={can("roles:update")} />
    </div>
  );
}
