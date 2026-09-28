import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DeadlineTypesAdmin, type RoleOption } from "@/components/settings/DeadlineTypesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import type { DeadlineType } from "@/components/workspace/DeadlineCreatePanel";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Fristtypen (Regel WS-01): Katalog mit Auslöser, Dauer (vom Betreiber
 *  eingetragen, zu verifizieren) und verantwortlicher Rolle. Lesen mit tenant_settings:read,
 *  Pflege mit tenant_settings:update. */
export default async function DeadlineTypesPage() {
  const t = await getTranslations("DeadlineTypes");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const [typesRes, rolesRes] = await Promise.all([
    serverFetch("/api/v1/workspace/deadline-types"),
    permissions.includes("roles:read") ? serverFetch("/api/v1/tenant/roles") : Promise.resolve(null),
  ]);
  const types = typesRes.ok ? ((await typesRes.json()) as DeadlineType[]) : [];
  const roles = rolesRes?.ok ? ((await rolesRes.json()) as { code: string; name: string }[]).map((r): RoleOption => ({ code: r.code, name: r.name })) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} breadcrumb={[{ href: "/einstellungen", label: t("settings") }]} />
      <DeadlineTypesAdmin initial={types} roles={roles} canManage={permissions.includes("tenant_settings:update")} />
    </div>
  );
}
