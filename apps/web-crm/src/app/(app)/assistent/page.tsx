import { getTranslations } from "next-intl/server";

import { Assistant } from "@/components/ai/Assistant";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function AssistantPage() {
  const t = await getTranslations("Ai");
  const { data, error, response } = await serverApi().GET("/api/v1/ai/conversations", {
    params: { query: {} },
  });
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("title")}</h1>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : (
        <Assistant initialConversations={data} />
      )}
    </div>
  );
}
