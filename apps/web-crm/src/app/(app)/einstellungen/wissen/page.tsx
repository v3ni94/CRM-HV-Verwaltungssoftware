import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { KnowledgeBase, type ExamplePage, type PlaybookRow } from "@/components/knowledge/KnowledgeBase";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

/** Wissensdatenbank (Betreiberauftrag 26.09.2026): gelernte Playbooks und Lernbeispiele
 *  (AiExample) aus Erledigungsnotizen und bestätigten Vorschlägen. Lesen mit
 *  tenant_settings:read; Deaktivieren nur mit communication:update. */
export default async function KnowledgePage() {
  const t = await getTranslations("Knowledge");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const [playbooks, examples] = await Promise.all([
    getJson<PlaybookRow[]>("/api/v1/mail/playbooks", []),
    getJson<ExamplePage>("/api/v1/ai/examples?per_page=50", { data: [], meta: { page: 1, per_page: 50, total: 0 } }),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className="text-sm text-muted">{t("description")}</p>
      <KnowledgeBase
        initialPlaybooks={playbooks}
        initialExamples={examples}
        canManage={permissions.includes("communication:update")}
      />
    </div>
  );
}
