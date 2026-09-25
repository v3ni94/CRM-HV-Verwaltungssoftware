import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DmsConnectionSettings, type DmsConnection } from "@/components/documents/DmsConnectionSettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** DMS-Anbindung (Einstellungen): Paperless-Zugangsdaten pflegen, Google Drive nur anzeigen.
 *  Immoware24 bleibt Master; hier wird ausschließlich die Anbindung des CRM an das
 *  Dokumentenmanagement konfiguriert. */
export default async function DmsSettingsPage() {
  const t = await getTranslations("DmsSettings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const connections = await api.GET("/api/v1/dms-connections");
  const list = (connections.data ?? []) as DmsConnection[];
  const paperless = list.find((c) => c.kind === "paperless") ?? null;
  const googleDrive = list.find((c) => c.kind === "google_drive") ?? null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <DmsConnectionSettings paperless={paperless} googleDrive={googleDrive} />
    </div>
  );
}
