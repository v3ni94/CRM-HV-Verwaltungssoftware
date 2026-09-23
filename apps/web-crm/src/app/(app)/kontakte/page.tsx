import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { BulkTagBar } from "@/components/workspace/BulkTagBar";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type Search = { q?: string; kind?: string; tag?: string; page?: string };

export default async function ContactsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const [t, tl, params] = await Promise.all([
    getTranslations("Contacts"),
    getTranslations("Labels"),
    searchParams,
  ]);
  const q = params.q?.trim() ?? "";
  const kind = params.kind === "person" || params.kind === "company" ? params.kind : undefined;
  const tag = params.tag?.trim() ?? "";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const { data, error, response } = await serverApi().GET("/api/v1/contacts", {
    params: {
      query: {
        ...(q ? { q } : {}),
        ...(kind ? { kind } : {}),
        ...(tag ? { tag } : {}),
        page,
        page_size: PAGE_SIZE,
      },
    },
  });
  redirectIfUnauthenticated(response);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const link = (target: number) => {
    const sp = new URLSearchParams();
    if (q) sp.set("q", q);
    if (kind) sp.set("kind", kind);
    if (tag) sp.set("tag", tag);
    sp.set("page", String(target));
    return `/kontakte?${sp}`;
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <div className="ml-auto">
          <Link href="/kontakte/neu" className={ui.primary}>
            {t("new")}
          </Link>
        </div>
      </div>
      <form method="get" action="/kontakte" role="search" className="flex flex-wrap items-end gap-2">
        <div className="min-w-64 flex-1">
          <label htmlFor="q" className={ui.label}>
            {t("search")}
          </label>
          <input id="q" name="q" type="search" defaultValue={q} placeholder={t("searchPlaceholder")} className={ui.input} />
        </div>
        <div>
          <label htmlFor="kind" className={ui.label}>
            {t("kind")}
          </label>
          <select id="kind" name="kind" defaultValue={kind ?? ""} className={ui.input}>
            <option value="">{t("allKinds")}</option>
            <option value="person">{tl("kind.person")}</option>
            <option value="company">{tl("kind.company")}</option>
          </select>
        </div>
        <div>
          <label htmlFor="tag" className={ui.label}>
            {t("tag")}
          </label>
          <input id="tag" name="tag" defaultValue={tag} className={ui.input} />
        </div>
        <button type="submit" className={ui.button}>
          {t("filter")}
        </button>
        <Link href="/kontakte" className="px-2 py-1.5 text-sm text-muted underline">
          {t("reset")}
        </Link>
      </form>

      <SavedFilters
        resource="contacts"
        basePath="/kontakte"
        current={Object.fromEntries(Object.entries({ q, kind: kind ?? "", tag }).filter(([, v]) => v))}
      />

      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <form id="contacts-bulk" className="flex flex-col gap-2">
          <BulkTagBar formId="contacts-bulk" />
          <table className="w-full border-collapse text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="w-6 py-1.5 pr-2 font-medium">
                  <span className="sr-only">{t("select")}</span>
                </th>
                <th className="py-1.5 pr-3 font-medium">{t("colName")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("colKind")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("colEmail")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("colPhone")}</th>
                <th className="py-1.5 pr-3 font-medium">{t("colCity")}</th>
                <th className="py-1.5 font-medium">{t("colTags")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} className="border-b border-border hover:bg-surface">
                  <td className="py-1.5 pr-2">
                    <input type="checkbox" name="bulk-id" value={c.id} aria-label={t("selectRow", { name: c.display_name })} />
                  </td>
                  <td className="py-1.5 pr-3">
                    <Link href={`/kontakte/${c.id}`} className="font-medium hover:underline">
                      {c.display_name}
                    </Link>
                    {c.blocked ? <span className="ml-2 text-xs text-danger-fg">{t("blocked")}</span> : null}
                    {c.completeness === "incomplete" ? <span className="ml-2 text-xs text-muted">{t("incomplete")}</span> : null}
                  </td>
                  <td className="py-1.5 pr-3">{tl(`kind.${c.kind}`)}</td>
                  <td className="py-1.5 pr-3">{c.primary_email ?? ""}</td>
                  <td className="py-1.5 pr-3">{c.primary_phone ?? ""}</td>
                  <td className="py-1.5 pr-3">{c.city ?? ""}</td>
                  <td className="py-1.5">{c.tags.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav className="flex items-center gap-3 text-sm" aria-label={t("page", { page, pages })}>
            <span className="text-muted">{t("total", { total: data.total })}</span>
            <span className="ml-auto">{t("page", { page, pages })}</span>
            {page > 1 ? (
              <Link href={link(page - 1)} className={ui.button}>
                {t("prev")}
              </Link>
            ) : null}
            {page < pages ? (
              <Link href={link(page + 1)} className={ui.button}>
                {t("next")}
              </Link>
            ) : null}
          </nav>
        </form>
      )}
    </div>
  );
}
