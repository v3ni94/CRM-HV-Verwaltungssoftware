import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { RulesSettings, type CategoryOption, type ClassificationRule } from "@/components/objektakte/RulesSettings";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** M35 Stufe 3 part 5: Einstellungen für die Regelstufe der dreistufigen Klassifikation
 * (docs/rules/M35-02.md). Nur `documents:read` nötig zum Ansehen; das Formular selbst prüft
 * `documents:update` serverseitig über den API-Aufruf (403 wird als Fehler angezeigt). */
export default async function ObjektakteRulesSettingsPage() {
  const t = await getTranslations("Objektakte");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("documents:read")) notFound();

  const [categoriesRes, rulesRes] = await Promise.all([
    api.GET("/api/v1/document-categories"),
    serverFetch("/api/v1/objektakte/classification-rules"),
  ]);
  const categories = (categoriesRes.data ?? []) as CategoryOption[];
  const rules = rulesRes.ok ? ((await rulesRes.json()) as ClassificationRule[]) : [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("rules.title")} description={t("rules.intro")} />
      <RulesSettings initial={rules} categories={categories} />
    </div>
  );
}
