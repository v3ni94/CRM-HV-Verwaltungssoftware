import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PortalFormsAdmin, type PortalFormTemplate } from "@/components/settings/PortalFormsAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Portalformulare (A56): Lesen mit tickets:read, Pflege mit tenant_settings:update (vom
 *  Backend geprüft; hier nur die Anzeige der Aktionen). */
export default async function PortalFormsPage() {
  const t = await getTranslations("PortalForms");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tickets:read")) notFound();
  const canManage = permissions.includes("tenant_settings:update");
  const res = await serverFetch("/api/v1/portal-admin/forms");
  const templates = res.ok ? ((await res.json()) as PortalFormTemplate[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <PortalFormsAdmin initialTemplates={templates} canManage={canManage} />
    </div>
  );
}
