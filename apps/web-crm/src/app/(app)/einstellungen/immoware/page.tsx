import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ImmowareSettings, type ImmowareConnection, type ImmowareSyncRun } from "@/components/immoware/ImmowareSettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

/** Immoware24-Anbindung (Einstellungen, M32): Verbindungsdaten fuer WebDAV, CardDAV und CalDAV,
 *  Verbindungstest und manuelles Anstossen der Abholung. Immoware24 bleibt Master, der Hub liest
 *  ausschliesslich, es gibt keinen Schreibpfad Richtung Immoware24. Bearbeiten nur mit
 *  immoware:update, sonst schreibgeschuetzt. */
export default async function ImmowareSettingsPage() {
  const t = await getTranslations("ImmowareSettings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("immoware:read")) notFound();
  const canManage = permissions.includes("immoware:update");
  const [connection, runs] = await Promise.all([
    api.GET("/api/v1/immoware/connection"),
    api.GET("/api/v1/immoware/sync/runs"),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <ImmowareSettings
        connection={connection.data as ImmowareConnection}
        runs={(runs.data ?? []) as ImmowareSyncRun[]}
        canManage={canManage}
      />
    </div>
  );
}
