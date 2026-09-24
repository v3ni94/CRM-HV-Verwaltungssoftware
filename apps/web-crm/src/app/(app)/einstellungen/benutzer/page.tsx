import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MembersAdmin } from "@/components/settings/MembersAdmin";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function MembersPage() {
  const t = await getTranslations("Members");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("members:read")) notFound();
  const [members, roles] = await Promise.all([api.GET("/api/v1/tenant/members"), api.GET("/api/v1/tenant/roles")]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("neverDeleted")}</p>
      <MembersAdmin
        initialMembers={members.data ?? []}
        roles={roles.data ?? []}
        canCreate={can("members:create")}
        canUpdate={can("members:update")}
      />
    </div>
  );
}
