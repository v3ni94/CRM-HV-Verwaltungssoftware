import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DmsConnectionSettings, type DmsConnection } from "@/components/documents/DmsConnectionSettings";
import type { OAuthStatus } from "@/components/mail/MailboxSettings";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { PageHeader } from "@/components/ui/PageHeader";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** DMS-Anbindung (Einstellungen): Paperless- und Google-Drive-Zugangsdaten pflegen.
 *  Immoware24 bleibt Master; hier wird ausschließlich die Anbindung des CRM an das
 *  Dokumentenmanagement konfiguriert. Google Drive lässt sich seit 1.9.1 per OAuth-Klick
 *  verbinden (gleicher OAuth-Client wie die Postfächer); der Rücksprung landet hier mit
 *  ?connected=drive&account=... bzw. ?oauth_error=. */
export default async function DmsSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string; account?: string; oauth_error?: string }>;
}) {
  const t = await getTranslations("DmsSettings");
  const params = await searchParams;
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [connections, oauth] = await Promise.all([
    api.GET("/api/v1/dms-connections"),
    api.GET("/api/v1/mail/oauth/google"),
  ]);
  const list = (connections.data ?? []) as DmsConnection[];
  const paperless = list.find((c) => c.kind === "paperless") ?? null;
  const googleDrive = list.find((c) => c.kind === "google_drive") ?? null;
  const connectedAccount = params.connected === "drive" ? params.account : undefined;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      {connectedAccount ? (
        <p className={ui.notice}>
          {googleDrive?.enabled
            ? t("connected", { account: connectedAccount })
            : t("connectedNeedsRootFolder", { account: connectedAccount })}
        </p>
      ) : null}
      {params.oauth_error ? (
        <p role="alert" className={ui.alert}>
          {t("oauthFailed", { reason: params.oauth_error })}
        </p>
      ) : null}
      <DmsConnectionSettings
        paperless={paperless}
        googleDrive={googleDrive}
        oauth={(oauth.data ?? { client_id: null, configured: false, source: null, redirect_uri: "" }) as OAuthStatus}
      />
    </div>
  );
}
