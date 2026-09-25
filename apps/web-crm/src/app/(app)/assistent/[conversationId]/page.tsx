import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AssistantMessage } from "@/components/ai/AssistantMessage";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

/** Read-only transcript of one chat: every question, answer, run and proposal with its
 *  decision. Writing happens in the chat bubble; audit readers only read. */
export default async function ConversationPage({ params }: { params: Promise<{ conversationId: string }> }) {
  const { conversationId } = await params;
  const t = await getTranslations("Ai");
  const { data, error, response } = await serverApi().GET("/api/v1/ai/conversations/{conversation_id}", {
    params: { path: { conversation_id: conversationId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const contextHref =
    data.context_type === "property" && data.context_id
      ? `/objekte/${data.context_id}`
      : data.context_type === "contact" && data.context_id
        ? `/kontakte/${data.context_id}`
        : null;
  const messages = data.messages ?? [];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <PageHeader
          eyebrow={t("transcript")}
          breadcrumb={[{ href: "/assistent", label: t("backToOverview") }]}
          title={data.title}
        />
        <dl className="mt-4 grid gap-x-6 gap-y-1 text-sm md:grid-cols-[auto_1fr]">
          <dt className="text-muted">{t("colUser")}</dt>
          <dd>{data.created_by_name ?? t("unknownUser")}</dd>
          <dt className="text-muted">{t("colStarted")}</dt>
          <dd className="tabular-nums">{formatDateTime(data.created_at)}</dd>
          <dt className="text-muted">{t("colContext")}</dt>
          <dd>
            {contextHref ? (
              <Link href={contextHref} className="hover:underline">
                {t(`context.${data.context_type}`)}
              </Link>
            ) : (
              t(`context.${data.context_type}`)
            )}
          </dd>
        </dl>
      </div>
      <p className={ui.notice}>{t("disclaimer")}</p>
      {messages.length === 0 ? (
        <EmptyState title={t("noMessages")} />
      ) : (
        <ul className="flex flex-col gap-3" aria-label={t("chat")}>
          {messages.map((m) => (
            <AssistantMessage key={m.id} message={m} />
          ))}
        </ul>
      )}
    </div>
  );
}
