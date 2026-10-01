import { getTranslations } from "next-intl/server";

import { GeneratedDocumentsList, type TemplateOption } from "@/components/documents/GeneratedDocumentsList";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Erzeugte Dokumente (GA04-11): Herkunft und Zustellung der Briefe, Filter nach Vorlage und Zeitraum. */
export default async function GeneratedDocumentsPage() {
  const t = await getTranslations("GeneratedDocuments");
  const res = await serverFetch("/api/v1/document-templates");
  redirectIfUnauthenticated(res);
  const templates = res.ok ? ((await res.json()) as TemplateOption[]) : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/dokumente", label: t("breadcrumb") }]} title={t("title")} description={t("intro")} />
      <GeneratedDocumentsList templates={templates} />
    </div>
  );
}
