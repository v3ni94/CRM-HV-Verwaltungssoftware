import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PortalFormsAdmin, type PortalFormTemplate } from "@/components/settings/PortalFormsAdmin";
import { PortalManagement, type PortalFeatures, type PortalStatistics } from "@/components/settings/PortalManagement";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Portalformulare (A56): Lesen mit tickets:read, Pflege mit tenant_settings:update (vom
 *  Backend geprüft; hier nur die Anzeige der Aktionen). */
export default async function PortalFormsPage() {
  const t = await getTranslations("PortalForms");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tickets:read")) notFound();
  const canManage = permissions.includes("tenant_settings:update");
  const res = await serverFetch("/api/v1/portal-admin/forms");
  const templates = res.ok ? ((await res.json()) as PortalFormTemplate[]) : [];
  const [featuresRes, statsRes] = await Promise.all([
    serverFetch("/api/v1/portal-admin/features"),
    serverFetch("/api/v1/portal-admin/statistics"),
  ]);
  const features = featuresRes.ok ? ((await featuresRes.json()) as PortalFeatures) : null;
  const statistics = statsRes.ok ? ((await statsRes.json()) as PortalStatistics) : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <PortalFormsAdmin initialTemplates={templates} canManage={canManage} />
      {features ? <PortalManagement initialFeatures={features} statistics={statistics} canManage={canManage} /> : null}
    </div>
  );
}
