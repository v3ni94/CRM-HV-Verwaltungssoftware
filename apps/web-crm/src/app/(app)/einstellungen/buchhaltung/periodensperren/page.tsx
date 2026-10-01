import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PeriodLockPanel, type PeriodLockRow, type PeriodLockSettings } from "@/components/settings/PeriodLockPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Buchhaltung, Periodensperren (P06-02, AE20): Sperre je Objekt und Zeitraum,
 *  Schalter und Aufhebung mit Vier-Augen-Freigabe. Die Seite bucht, versendet und löscht nichts. */
export default async function PeriodLockPage() {
  const t = await getTranslations("PeriodLocks");
  const tt = await getTranslations("Settings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const [settingsRes, listRes] = await Promise.all([
    serverFetch("/api/v1/accounting/period-locks/settings"),
    serverFetch("/api/v1/accounting/period-locks"),
  ]);
  const settings = settingsRes.ok ? ((await settingsRes.json()) as PeriodLockSettings) : null;
  const rows = listRes.ok ? ((await listRes.json()) as PeriodLockRow[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={tt("periodLocks.title")} description={tt("periodLocks.description")} />
      <p className="text-sm text-muted-foreground">{t("decisionOpen")}</p>
      <PeriodLockPanel
        initialSettings={settings}
        initialRows={rows}
        canApprove={permissions.includes("accounting:approve")}
        canSettings={permissions.includes("tenant_settings:update")}
      />
    </div>
  );
}
