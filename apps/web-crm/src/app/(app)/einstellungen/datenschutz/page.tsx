import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { AccessExportSettings, type AccessExportSettingsData } from "@/components/contacts/AccessExportSettings";
import { ConsentPolicySettings } from "@/components/privacy/ConsentPolicySettings";
import { PrivacyAdmin } from "@/components/privacy/PrivacyAdmin";
import { PrivacyOversight } from "@/components/privacy/PrivacyOversight";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Datenschutz (Abschnitt 16): Löschprofile, Löschanträge mit Vier-Augen, Register und
 *  Verzeichnis-Entwurf. Lesen mit privacy:read, Pflege privacy:manage, Freigabe privacy:approve
 *  (vom Backend geprüft). */
export default async function PrivacyPage() {
  const t = await getTranslations("PrivacyAdmin");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("privacy:read")) notFound();
  // AE33 (AC07-01): Umfang der Auskunft; nur mit Leserecht auf die Mandanteneinstellungen.
  const scopeRes = permissions.includes("tenant_settings:read") ? await serverFetch("/api/v1/contact-access-export-settings") : null;
  const scope = scopeRes?.ok ? ((await scopeRes.json()) as AccessExportSettingsData) : null;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <PrivacyAdmin canManage={permissions.includes("privacy:manage")} canApprove={permissions.includes("privacy:approve")} />
      <PrivacyOversight canApprove={permissions.includes("privacy:approve")} />
      {permissions.includes("contacts:read") ? <ConsentPolicySettings canEdit={permissions.includes("contacts:approve")} /> : null}
      {scope ? <AccessExportSettings initial={scope} canEdit={permissions.includes("tenant_settings:update")} /> : null}
    </div>
  );
}
