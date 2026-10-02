import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DocumentBulkLink } from "@/components/aj17/DocumentBulkLink";
import { DocumentBulkBar } from "@/components/workspace/DocumentBulkBar";
import { DocumentListFilter, draftFilterOf } from "@/components/documents/DocumentListFilter";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { ResponsiveList } from "@/components/ui/ResponsiveList";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { q?: string; entwurf?: string; seite?: string };

const PAGE_SIZE = 50;

/** Document list (full text search, draft filter A83). Document reads stay outside the BFF
 *  allowlist, therefore the page is read server side with a plain GET form. */
export default async function DocumentsPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("DocumentList");
  const q = (params.q ?? "").trim();
  const draft = draftFilterOf(params.entwurf);
  const page = Math.max(1, Number.parseInt(params.seite ?? "1", 10) || 1);
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/documents", {
    params: {
      query: {
        ...(q.length >= 2 ? { q } : {}),
        ...(draft ? { is_draft: draft === "true" } : {}),
        page,
        page_size: PAGE_SIZE,
      },
    },
  });
  redirectIfUnauthenticated(response);
  const items = data?.items ?? [];
  const canLinkDocuments = ((await getMe()).data?.permissions ?? []).includes("documents:update");
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const href = (p: number) => {
    const s = new URLSearchParams();
    if (q) s.set("q", q);
    if (draft) s.set("entwurf", draft);
    if (p > 1) s.set("seite", String(p));
    const query = s.toString();
    return query ? `/dokumente?${query}` : "/dokumente";
  };
  return (
    <div className={ui.pageGap}>
      <PageHeader eyebrow={t("area")} title={t("title")} description={t("intro")} />
      <p className={ui.small}>
        <Link href="/dokumente/loeschvorschlaege">{t("deletionProposalsLink")}</Link>
        {" · "}
        <Link href="/dokumente/briefe">{t("lettersLink")}</Link>
        {" · "}
        <Link href="/dokumente/erzeugt">{t("generatedLink")}</Link>
      </p>
      <DocumentListFilter q={q} draft={draft} />
      <DocumentBulkLink canEdit={canLinkDocuments} />
      <SavedFilters resource="documents" basePath="/dokumente" current={Object.fromEntries(Object.entries({ q, entwurf: params.entwurf ?? "" }).filter(([, v]) => v))} />
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : items.length === 0 ? (
        <EmptyState title={draft === "true" ? t("emptyDrafts") : t("empty")} />
      ) : (
        <div id="documents-bulk" className="flex flex-col gap-3">
        <DocumentBulkBar formId="documents-bulk" />
        <ResponsiveList
          rows={items}
          keyOf={(d) => d.id}
          testId="documents"
          card={(d) => (
            <div className="flex flex-col gap-1">
              <input type="checkbox" name="bulk-id" value={d.id} aria-label={t("select", { title: d.title })} />
              <Link href={`/dokumente/${d.id}`} className="font-medium hover:underline [overflow-wrap:anywhere]">
                {d.title}
              </Link>
              <span className="text-sm text-muted [overflow-wrap:anywhere]">{d.filename}</span>
              <span className="text-sm tabular-nums text-muted">{formatDate(d.created_at)}</span>
              {d.is_draft ? (
                <span>
                  <span className={ui.badgeWarning}>{t("draftBadge")}</span>
                </span>
              ) : null}
            </div>
          )}
          table={
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("colSelect")}</th>
                <th>{t("colTitle")}</th>
                <th>{t("colFilename")}</th>
                <th>{t("colCreated")}</th>
                <th>{t("colStatus")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((d) => (
                <tr key={d.id}>
                  <td>
                    <input type="checkbox" name="bulk-id" value={d.id} aria-label={t("select", { title: d.title })} />
                  </td>
                  <td>
                    <Link href={`/dokumente/${d.id}`} className="hover:underline">
                      {d.title}
                    </Link>
                    {d.snippet ? <p className={ui.help}>{d.snippet.replaceAll("<<", "").replaceAll(">>", "")}</p> : null}
                  </td>
                  <td>{d.filename}</td>
                  <td className="tabular-nums">{formatDate(d.created_at)}</td>
                  <td>{d.is_draft ? <span className={ui.badgeWarning}>{t("draftBadge")}</span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
          }
        />
        </div>
      )}
      {data && pages > 1 ? (
        <nav className="flex items-center gap-3 text-sm" aria-label={t("pagination")}>
          {page > 1 ? (
            <Link href={href(page - 1)} className={ui.button}>
              {t("previous")}
            </Link>
          ) : null}
          <span className="text-muted">{t("pageOf", { page, pages, total })}</span>
          {page < pages ? (
            <Link href={href(page + 1)} className={ui.button}>
              {t("next")}
            </Link>
          ) : null}
        </nav>
      ) : null}
    </div>
  );
}
