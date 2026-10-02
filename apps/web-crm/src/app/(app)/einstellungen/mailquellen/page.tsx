import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MailSourcesAdmin, type MailSource } from "@/components/settings/MailSourcesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Mail sources of the legacy program with secret rotation and receipt log (AE38, AF19).
 *  Reading needs tenant_settings:read, changing tenant_settings:update (checked by the API). */
export default async function MailSourcesPage() {
  const t = await getTranslations("AF19");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const res = await serverFetch("/api/v1/mail/inbound/sources");
  const initial: MailSource[] = res.ok ? ((await res.json()) as MailSource[]) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("mail.title")} description={t("mail.intro")} />
      <MailSourcesAdmin initial={initial} loadFailed={!res.ok} canManage={permissions.includes("tenant_settings:update")} />
    </div>
  );
}
