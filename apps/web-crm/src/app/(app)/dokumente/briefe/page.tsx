import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { LetterTemplates, type LetterTemplate } from "@/components/documents/LetterTemplates";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Briefe und Briefvorlagen (11.3, M6-01): Brief aus Vorlage mit Vorschau, Serienbrief,
 *  Vorlagenverwaltung mit Versionen. Erzeugte Briefe werden abgelegt, nicht versandt. */
export default async function LettersPage() {
  const t = await getTranslations("LetterTemplates");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const perms = me.data?.permissions ?? [];
  if (!perms.includes("documents:create")) notFound();
  const res = await serverFetch("/api/v1/document-templates");
  const templates = res.ok ? ((await res.json()) as LetterTemplate[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/dokumente", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <LetterTemplates templates={templates} canManage={perms.includes("tenant_settings:update")} />
    </div>
  );
}
