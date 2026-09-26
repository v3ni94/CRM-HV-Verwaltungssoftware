import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { RulesSettings, type CategoryOption, type ClassificationRule } from "@/components/objektakte/RulesSettings";
import { SyncStatus, type SyncState } from "@/components/objektakte/SyncStatus";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** M35 Stufe 3 part 5: Einstellungen für die Regelstufe der dreistufigen Klassifikation
 * (docs/rules/M35-02.md). Nur `objektakte:read` nötig zum Ansehen; das Formular selbst prüft
 * `objektakte:approve` (Anlegen/Ändern) bzw. `objektakte:delete` serverseitig über den
 * API-Aufruf (403 wird als Fehler angezeigt, M35 Stufe 4, docs/rules/M35-03.md). Stufe 5:
 * darunter der Synchronisationsstand des täglichen Differenzimports (Schalter und Pfad nur mit
 * `tenant_settings:update`, manueller Lauf mit `documents:create`). */
export default async function ObjektakteRulesSettingsPage() {
  const t = await getTranslations("Objektakte");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("objektakte:read")) notFound();

  const can = (p: string) => me.data?.permissions.includes(p) ?? false;

  const [categoriesRes, rulesRes, syncRes] = await Promise.all([
    api.GET("/api/v1/document-categories"),
    serverFetch("/api/v1/objektakte/classification-rules"),
    serverFetch("/api/v1/objektakte/sync"),
  ]);
  const categories = (categoriesRes.data ?? []) as CategoryOption[];
  const rules = rulesRes.ok ? ((await rulesRes.json()) as ClassificationRule[]) : [];
  const sync = syncRes.ok ? ((await syncRes.json()) as SyncState) : null;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("rules.title")} description={t("rules.intro")} />
      <RulesSettings initial={rules} categories={categories} />
      {sync ? <SyncStatus initial={sync} canEdit={can("tenant_settings:update")} canRun={can("documents:create")} /> : null}
    </div>
  );
}
