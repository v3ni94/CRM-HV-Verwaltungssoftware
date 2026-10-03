import { getTranslations } from "next-intl/server";

import { AvailabilityAdmin } from "@/components/platform/AvailabilityAdmin";
import { AvailabilitySelfMeasurement } from "@/components/platform/AvailabilitySelfMeasurement";
import { MaintenanceAdmin } from "@/components/platform/MaintenanceAdmin";
import { RestoreReportView } from "@/components/platform/RestoreReportView";
import { ScaleMonitor } from "@/components/platform/ScaleMonitor";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** AD10 (GB16-01, GB16-02): Wartungsfenster und Verfügbarkeit, nur für Plattformadministratoren. */
export default async function Page() {
  const t = await getTranslations("AD10");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.is_platform_admin) return <p className={ui.alert}>{t("forbidden")}</p>;
  return (
    <div className={ui.pageGap}>
      <PageHeader title={t("title")} description={t("intro")} />
      <MaintenanceAdmin />
      <AvailabilitySelfMeasurement />
      <AvailabilityAdmin />
      <ScaleMonitor />
      <RestoreReportView />
    </div>
  );
}
