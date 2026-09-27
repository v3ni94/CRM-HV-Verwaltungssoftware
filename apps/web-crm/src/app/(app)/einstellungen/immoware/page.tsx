import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ImmowareSettings, type ImmowareConnection, type ImmowareSyncRun } from "@/components/immoware/ImmowareSettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PageHeader } from "@/components/ui/PageHeader";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Immoware24-Anbindung (Einstellungen, M32): Verbindungsdaten fuer WebDAV, CardDAV und CalDAV,
 *  Verbindungstest und manuelles Anstossen der Abholung. Immoware24 bleibt Master, der Hub liest
 *  ausschliesslich, es gibt keinen Schreibpfad Richtung Immoware24. Bearbeiten nur mit
 *  immoware:update, sonst schreibgeschuetzt. */
export default async function ImmowareSettingsPage() {
  const t = await getTranslations("ImmowareSettings");
  const api = serverApi();
  const me = await getMe();
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
      <div className="flex flex-wrap gap-2">
        <Link href="/immoware" className={ui.button}>
          {t("openWorkspace")}
        </Link>
        <Link href="/immoware/lernphase" className={ui.button}>
          {t("openLearning")}
        </Link>
      </div>
      <ImmowareSettings
        connection={connection.data as ImmowareConnection}
        runs={(runs.data ?? []) as ImmowareSyncRun[]}
        canManage={canManage}
      />
    </div>
  );
}
