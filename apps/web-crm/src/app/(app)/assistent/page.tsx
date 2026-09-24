import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { scope?: string; user?: string; from?: string; to?: string; q?: string };

/** Audit trail of the assistant (operator 24.09.2026): every chat, answer and proposal is
 *  traceable here. The chat bubble on each page is the entry point for new requests; audit
 *  readers (audit:read) see the chats of all users chronologically and can filter them. */
export default async function AssistantPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("Ai");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const canAudit = me.data?.permissions.includes("audit:read") ?? false;
  const scope: "all" | "own" = canAudit && params.scope !== "own" ? "all" : "own";
  const query = {
    scope,
    limit: 200,
    ...(scope === "all" && params.user ? { user_id: params.user } : {}),
    ...(params.from ? { date_from: params.from } : {}),
    ...(params.to ? { date_to: params.to } : {}),
    ...(params.q ? { q: params.q } : {}),
  };
  const [{ data, error, response }, members] = await Promise.all([
    api.GET("/api/v1/ai/conversations", { params: { query } }),
    canAudit ? api.GET("/api/v1/tenant/members") : Promise.resolve(null),
  ]);
  const users = members?.data ?? [];
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className={ui.subtitle}>{t("area")}</p>
        <h1 className={ui.title}>{t("title")}</h1>
        <p className="mt-1 text-sm text-muted">{t("auditIntro")}</p>
      </div>
      <p className={ui.notice}>{t("bubbleHint")}</p>
      <form className="grid gap-3 md:grid-cols-[auto_1fr_auto_auto_auto] md:items-end" role="search">
        {canAudit ? (
          <div>
            <label htmlFor="scope" className={ui.label}>
              {t("filterScope")}
            </label>
            <select id="scope" name="scope" defaultValue={scope} className={ui.input}>
              <option value="all">{t("scopeAll")}</option>
              <option value="own">{t("scopeOwn")}</option>
            </select>
          </div>
        ) : null}
        {canAudit ? (
          <div>
            <label htmlFor="user" className={ui.label}>
              {t("filterUser")}
            </label>
            <select id="user" name="user" defaultValue={params.user ?? ""} className={ui.input}>
              <option value="">{t("allUsers")}</option>
              {users.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span />
        )}
        <div>
          <label htmlFor="from" className={ui.label}>
            {t("filterFrom")}
          </label>
          <input id="from" name="from" type="date" defaultValue={params.from ?? ""} className={ui.input} />
        </div>
        <div>
          <label htmlFor="to" className={ui.label}>
            {t("filterTo")}
          </label>
          <input id="to" name="to" type="date" defaultValue={params.to ?? ""} className={ui.input} />
        </div>
        <div className="flex gap-2">
          <input name="q" defaultValue={params.q ?? ""} placeholder={t("filterText")} aria-label={t("filterText")} className={ui.input} />
          <button type="submit" className={ui.button}>
            {t("filter")}
          </button>
        </div>
      </form>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">{t("noConversations")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="conversations">
            <thead>
              <tr>
                <th>{t("colStarted")}</th>
                {scope === "all" ? <th>{t("colUser")}</th> : null}
                <th>{t("colTitle")}</th>
                <th>{t("colContext")}</th>
                <th className="text-right">{t("colMessages")}</th>
                <th>{t("colLast")}</th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id}>
                  <td className="tabular-nums">
                    <Link href={`/assistent/${c.id}`} className="font-medium hover:underline">
                      {formatDateTime(c.created_at)}
                    </Link>
                  </td>
                  {scope === "all" ? <td>{c.created_by_name ?? t("unknownUser")}</td> : null}
                  <td>
                    <Link href={`/assistent/${c.id}`} className="hover:underline">
                      {c.title}
                    </Link>
                  </td>
                  <td>
                    <span className={ui.badge}>{t(`context.${c.context_type}`)}</span>
                  </td>
                  <td className="text-right tabular-nums">{c.message_count}</td>
                  <td className="text-muted">{formatDateTime(c.last_message_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
