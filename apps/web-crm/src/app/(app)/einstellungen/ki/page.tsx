import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ProviderSettings } from "@/components/ai/ProviderSettings";
import { UsagePanel } from "@/components/ai/UsagePanel";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function AiSettingsPage() {
  const t = await getTranslations("AiSettings");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const [providers, usage] = await Promise.all([api.GET("/api/v1/ai/providers"), api.GET("/api/v1/ai/usage")]);
  const anthropic = providers.data?.find((p) => p.provider === "anthropic") ?? null;
  const openai = providers.data?.find((p) => p.provider === "openai") ?? null;
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      <p className="text-sm text-muted">{t("intro")}</p>
      {usage.data ? <UsagePanel usage={usage.data} /> : null}
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
    </div>
  );
}
