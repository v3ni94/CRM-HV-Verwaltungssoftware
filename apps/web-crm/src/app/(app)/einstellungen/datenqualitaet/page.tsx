import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DataQualityActions } from "@/components/settings/DataQualityActions";
import { DataQualityReport, type DataQualityReportData } from "@/components/settings/DataQualityReport";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Datenqualität (Erfassungsstandards ES-01 to ES-11): report of
 *  `GET /data-quality/report`; sections for properties and deadlines depend on the permission. */
export default async function DataQualityPage() {
  const t = await getTranslations("DataQuality");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("contacts:read")) notFound();
  const res = await serverFetch("/api/v1/data-quality/report");
  const report = res.ok ? ((await res.json()) as DataQualityReportData) : null;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <DataQualityActions canRecompute={me.data.permissions.includes("contacts:update")} />
      <DataQualityReport report={report} />
    </div>
  );
}
