import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PrivacyAdmin } from "@/components/privacy/PrivacyAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
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
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <PrivacyAdmin canManage={permissions.includes("privacy:manage")} canApprove={permissions.includes("privacy:approve")} />
    </div>
  );
}
