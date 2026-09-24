import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { MailWorkspace } from "@/components/mail/MailWorkspace";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Mail (M20): reads and drafts on top of the connected mailboxes (M20-01). Message state and
 *  the four-eyes approval flow are loaded client side; this page only checks the permission. */
export default async function MailPage() {
  const t = await getTranslations("Mail");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("communication:read")) notFound();
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <MailWorkspace canApprove={permissions.includes("communication:approve")} canReadMembers={permissions.includes("members:read")} />
    </div>
  );
}
