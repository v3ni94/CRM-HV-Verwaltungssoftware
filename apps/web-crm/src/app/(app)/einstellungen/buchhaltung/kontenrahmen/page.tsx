import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ChartReleaseAdmin, type ChartTemplate } from "@/components/settings/ChartReleaseAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Buchhaltung, Kontenrahmen (M10-01/M10-02, V8): Status Entwurf, zur Prüfung,
 *  freigegeben mit Freigabedialog, Versionsverlauf und Export als CSV oder PDF für die
 *  Steuerberatung. Nur ein freigegebener Kontenrahmen öffnet die Freigabestufe G1. */
export default async function ChartReleasePage() {
  const t = await getTranslations("ChartRelease");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const res = await serverFetch("/api/v1/accounting/templates");
  const templates = res.ok ? ((await res.json()) as ChartTemplate[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <ChartReleaseAdmin
        initial={templates}
        canManage={permissions.includes("accounting:update")}
        canApprove={permissions.includes("accounting:approve")}
      />
    </div>
  );
}
