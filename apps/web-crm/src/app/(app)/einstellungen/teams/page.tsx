import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TeamsAdmin, type TeamMemberOption } from "@/components/settings/TeamsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Teams der Tickets (M19-02): Anzeige mit tickets:read, Anlegen, Ändern und Löschen mit
 *  tickets:approve (vom Backend geprüft). Die Mitgliederauswahl braucht members:read, ohne das
 *  Recht zeigt die Seite die Teams mit den Benutzerkennungen. */
export default async function TeamsPage() {
  const t = await getTranslations("TeamsAdmin");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tickets:read")) notFound();
  const membersRes = permissions.includes("members:read") ? await serverFetch("/api/v1/tenant/members") : null;
  const members: TeamMemberOption[] = membersRes?.ok
    ? ((await membersRes.json()) as { user_id: string; display_name: string | null; email: string }[]).map((m) => ({
        id: m.user_id,
        label: m.display_name || m.email,
      }))
    : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }, { label: t("title") }]}
        title={t("title")}
      />
      <TeamsAdmin members={members} canManage={permissions.includes("tickets:approve")} />
    </div>
  );
}
