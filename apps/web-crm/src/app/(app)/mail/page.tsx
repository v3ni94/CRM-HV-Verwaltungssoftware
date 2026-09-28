import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { MailWorkspace } from "@/components/mail/MailWorkspace";
import { RuleProposalsBadge } from "@/components/settings/RuleProposals";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Mail (M20): reads and drafts on top of the connected mailboxes (M20-01). Message state and
 *  the four-eyes approval flow are loaded client side; this page only checks the permission. */
export default async function MailPage() {
  const t = await getTranslations("Mail");
  const tPlaybooks = await getTranslations("MailPlaybooks");
  const tPostal = await getTranslations("PostalOutbox");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("communication:read")) notFound();
  // Lern-Workflow (Regel M9-11): Hinweis auf offene Regelvorschläge, nur mit Leserecht.
  let proposals = 0;
  if (permissions.includes("tenant_settings:read")) {
    const res = await serverFetch("/api/v1/automation/rule-proposals?status=proposed&limit=500");
    if (res.ok) proposals = ((await res.json()) as unknown[]).length;
  }
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        action={
          <div className="flex flex-wrap gap-2">
            <RuleProposalsBadge count={proposals} />
            <Link href="/mail/postausgang" className={ui.button}>
              {tPostal("title")}
            </Link>
            <Link href="/mail/playbooks" className={ui.button}>
              {tPlaybooks("title")}
            </Link>
          </div>
        }
      />
      <MailWorkspace canApprove={permissions.includes("communication:approve")} canReadMembers={permissions.includes("members:read")} />
    </div>
  );
}
