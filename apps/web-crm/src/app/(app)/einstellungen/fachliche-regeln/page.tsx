import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { BusinessRulesList } from "@/components/settings/BusinessRulesList";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { readPaths, visibleRules } from "@/lib/business-rules";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Fachliche Regeln (Welle 16, AE39): alle Mandantenschalter für fachlich offene
 *  Entscheidungen an einer Stelle, mit aktuellem Wert, Varianten, Standard und Verweis auf die
 *  offene Frage in docs/OPEN_QUESTIONS.md. Geändert wird nur dort, wo der Endpunkt ein PUT oder
 *  PATCH anbietet und das Recht vorliegt. Die Seite bucht, versendet und löscht nichts. */
export default async function BusinessRulesPage() {
  const t = await getTranslations("BusinessRules");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  const rules = visibleRules(permissions);
  if (rules.length === 0) notFound();
  const paths = readPaths(rules);
  const results = await Promise.all(
    paths.map(async (path) => {
      try {
        const res = await serverFetch(`/api/v1/${path}`);
        return [path, res.ok ? ((await res.json()) as unknown) : null] as const;
      } catch {
        return [path, null] as const;
      }
    }),
  );
  const docs: Record<string, unknown> = Object.fromEntries(results);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <p className="text-sm text-muted">{t("intro")}</p>
      <BusinessRulesList initialDocs={docs} permissions={permissions} />
    </div>
  );
}
