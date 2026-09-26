import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AutomationAdmin, type Option, type Rule, type Run } from "@/components/settings/AutomationAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Regel-Engine Stufe 1 (A38): Anzeige mit tenant_settings:read oder tickets:read, Pflege mit
 *  tenant_settings:update (vom Backend geprüft; hier nur die Anzeige der Aktionen). */
export default async function AutomationPage() {
  const t = await getTranslations("Automation");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read") && !permissions.includes("tickets:read")) notFound();
  const canManage = permissions.includes("tenant_settings:update");

  const [rulesRes, runsRes, metaRes, templatesRes, rolesRes, membersRes] = await Promise.all([
    serverFetch("/api/v1/automation/rules"),
    serverFetch("/api/v1/automation/runs?limit=50"),
    serverFetch("/api/v1/automation/meta"),
    serverFetch("/api/v1/tickets/templates"),
    canManage ? serverFetch("/api/v1/tenant/roles") : Promise.resolve(null),
    canManage ? serverFetch("/api/v1/tenant/members") : Promise.resolve(null),
  ]);
  const rules = rulesRes.ok ? ((await rulesRes.json()) as Rule[]) : [];
  const runs = runsRes.ok ? ((await runsRes.json()) as { items: Run[] }).items : [];
  const meta = metaRes.ok ? ((await metaRes.json()) as { event_types: string[] }) : { event_types: [] };
  const templates: Option[] = templatesRes.ok
    ? ((await templatesRes.json()) as { id: string; category: string; title: string }[]).map((x) => ({ id: x.id, label: `${x.category}: ${x.title}` }))
    : [];
  const roles: Option[] = rolesRes?.ok ? ((await rolesRes.json()) as { code: string; name: string }[]).map((r) => ({ id: r.code, label: r.name })) : [];
  const members: Option[] = membersRes?.ok
    ? ((await membersRes.json()) as { user_id: string; display_name: string | null; email: string }[]).map((m) => ({ id: m.user_id, label: m.display_name || m.email }))
    : [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("pageDescription")} />
      <AutomationAdmin initialRules={rules} initialRuns={runs} pickers={{ templates, roles, members, eventTypes: meta.event_types }} canManage={canManage} />
    </div>
  );
}
