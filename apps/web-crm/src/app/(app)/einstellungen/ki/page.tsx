import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { KnowledgeSettings } from "@/components/ai/KnowledgeSettings";
import { ProviderSettings } from "@/components/ai/ProviderSettings";
import { RoutingSettings, type Strategy } from "@/components/ai/RoutingSettings";
import { UsagePanel } from "@/components/ai/UsagePanel";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function AiSettingsPage() {
  const t = await getTranslations("AiSettings");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [providers, usage, routing, knowledge, properties] = await Promise.all([
    api.GET("/api/v1/ai/providers"),
    api.GET("/api/v1/ai/usage"),
    api.GET("/api/v1/ai/routing"),
    api.GET("/api/v1/ai/knowledge"),
    api.GET("/api/v1/properties"),
  ]);
  const anthropic = providers.data?.find((p) => p.provider === "anthropic") ?? null;
  const openai = providers.data?.find((p) => p.provider === "openai") ?? null;
  const propertyOptions = (properties.data?.items ?? []).map((p) => ({ id: p.id, number: p.number, name: p.name }));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className="text-sm text-muted">{t("intro")}</p>
      {usage.data ? <UsagePanel usage={usage.data} /> : null}
      <RoutingSettings initial={(routing.data?.strategy ?? "anthropic_first") as Strategy} />
      {!providers.data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(providers.error as Problem | undefined, providers.response.status)}
        </p>
      ) : (
        <>
          <ProviderSettings provider="anthropic" initial={anthropic} />
          <ProviderSettings provider="openai" initial={openai} />
        </>
      )}
      <p className="text-xs text-muted">{t("openaiHint")}</p>
      <KnowledgeSettings initial={knowledge.data ?? []} properties={propertyOptions} />
    </div>
  );
}
