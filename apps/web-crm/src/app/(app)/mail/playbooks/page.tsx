import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PlaybookManager, type Playbook } from "@/components/mail/PlaybookManager";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Playbooks (M20 Übernahme aus dem Immoware Hub): aus geschlossenen Tickets gelernte Abläufe,
 *  je Mail als Vorschlag genutzt. Entwürfe aus dem Lernen werden hier freigegeben. */
export default async function MailPlaybooksPage() {
  const t = await getTranslations("MailPlaybooks");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("communication:read")) notFound();
  const playbooks = await api.GET("/api/v1/mail/playbooks");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        breadcrumb={[{ href: "/mail", label: "Mail" }, { label: t("title") }]}
      />
      <PlaybookManager
        playbooks={(playbooks.data ?? []) as Playbook[]}
        canWrite={permissions.includes("communication:update")}
        canDelete={permissions.includes("tenant_settings:update")}
      />
      <Link href="/mail" className="text-sm hover:underline">
        {t("backToMail")}
      </Link>
    </div>
  );
}
