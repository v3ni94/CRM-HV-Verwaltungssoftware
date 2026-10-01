import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  TakeoverTicketDefaultsCard,
  type TakeoverDefaults,
  type TakeoverOption,
} from "@/components/settings/TakeoverTicketDefaultsCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Übernahme-Tickets (V06-01): Lesen mit tenant_settings:read, Ändern mit
 *  tenant_settings:update. Teams brauchen tickets:read, Benutzer members:read; fehlt ein Recht,
 *  bleibt die jeweilige Auswahl auf den gespeicherten Wert beschränkt. */
export default async function TakeoverTicketDefaultsPage() {
  const t = await getTranslations("TakeoverTicketDefaults");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const [defRes, teamRes, memberRes] = await Promise.all([
    serverFetch("/api/v1/onboarding/takeover-ticket-defaults"),
    permissions.includes("tickets:read") ? serverFetch("/api/v1/teams") : Promise.resolve(null),
    permissions.includes("members:read") ? serverFetch("/api/v1/tenant/members") : Promise.resolve(null),
  ]);
  const defaults: TakeoverDefaults = defRes.ok
    ? ((await defRes.json()) as TakeoverDefaults)
    : { team_id: null, assignee_user_id: null };
  const teams: TakeoverOption[] =
    teamRes && teamRes.ok
      ? ((await teamRes.json()) as { id: string; name: string }[]).map((x) => ({ id: x.id, label: x.name }))
      : [];
  const members: TakeoverOption[] =
    memberRes && memberRes.ok
      ? ((await memberRes.json()) as { user_id: string; display_name: string; status: string }[])
          .filter((m) => m.status === "active")
          .map((m) => ({ id: m.user_id, label: m.display_name }))
      : [];
  const incomplete = !(teamRes && teamRes.ok) || !(memberRes && memberRes.ok);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} breadcrumb={[{ href: "/einstellungen", label: t("settings") }]} />
      <TakeoverTicketDefaultsCard
        defaults={defaults}
        teams={teams}
        members={members}
        canManage={permissions.includes("tenant_settings:update")}
        incomplete={incomplete}
      />
    </div>
  );
}
