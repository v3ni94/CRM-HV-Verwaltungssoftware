import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PageHeader } from "@/components/ui/PageHeader";
import { BulkTagBar } from "@/components/workspace/BulkTagBar";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { RolePills } from "@/components/contacts/RolePills";
import { CONTACT_ROLES, parseRoleFilter } from "@/lib/contact-schema";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type Search = { q?: string; kind?: string; tag?: string; role?: string; page?: string };

export default async function ContactsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const [t, tl, params] = await Promise.all([
    getTranslations("Contacts"),
    getTranslations("Labels"),
    searchParams,
  ]);
  const q = params.q?.trim() ?? "";
  const kind = params.kind === "person" || params.kind === "company" ? params.kind : undefined;
  const tag = params.tag?.trim() ?? "";
  const role = parseRoleFilter(params.role);
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  const { data, error, response } = await serverApi().GET("/api/v1/contacts", {
    params: {
      query: {
        ...(q ? { q } : {}),
        ...(kind ? { kind } : {}),
        ...(tag ? { tag } : {}),
        ...(role ? { role } : {}),
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
    if (role) sp.set("role", role);
    sp.set("page", String(target));
    return `/kontakte?${sp}`;
  };
  const roleLink = (target?: string) => {
    const sp = new URLSearchParams();
    if (q) sp.set("q", q);
    if (kind) sp.set("kind", kind);
    if (tag) sp.set("tag", tag);
    if (target) sp.set("role", target);
    return `/kontakte?${sp}`;
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("title")}
        action={
          <Link href="/kontakte/neu" className={ui.primary}>
            {t("new")}
          </Link>
        }
      />
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

      <div className="flex flex-wrap gap-2" role="group" aria-label={t("role")}>
        <Link
          href={roleLink()}
          aria-current={!role ? "true" : undefined}
          className={`rounded-full px-3 py-1 text-xs ${!role ? "bg-accent text-accent-fg" : "bg-surface text-muted hover:text-fg"}`}
        >
          {t("allRoles")}
        </Link>
        {CONTACT_ROLES.map((r) => (
          <Link
            key={r}
            href={roleLink(r)}
            aria-current={role === r ? "true" : undefined}
            className={`rounded-full px-3 py-1 text-xs ${role === r ? "bg-accent text-accent-fg" : "bg-surface text-muted hover:text-fg"}`}
          >
            {tl(`role.${r}`)}
          </Link>
        ))}
      </div>

      <SavedFilters
        resource="contacts"
        basePath="/kontakte"
        current={Object.fromEntries(Object.entries({ q, kind: kind ?? "", tag, role: role ?? "" }).filter(([, v]) => v))}
      />

      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : data.items.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <>
          <ul className="flex flex-col gap-2 sm:hidden" data-testid="contacts-cards">
            {data.items.map((c) => (
              <li key={c.id} className={ui.cardLink} data-testid="contact-card">
                <Link href={`/kontakte/${c.id}`} className="flex flex-col gap-1">
                  <span className="font-medium">
                    {c.display_name}
                    {c.blocked ? <span className="ml-2 text-xs text-danger-fg">{t("blocked")}</span> : null}
                    {c.completeness === "incomplete" ? <span className="ml-2 text-xs text-muted">{t("incomplete")}</span> : null}
                  </span>
                  <span className="text-sm text-muted">{tl(`kind.${c.kind}`)}</span>
                  <RolePills roles={c.roles} />
                  {c.primary_email ? <span className="text-sm text-muted">{c.primary_email}</span> : null}
                  {c.primary_phone ? <span className="text-sm text-muted">{c.primary_phone}</span> : null}
                  {c.city ? <span className="text-sm text-muted">{c.city}</span> : null}
                </Link>
              </li>
            ))}
          </ul>
          <form id="contacts-bulk" className="hidden flex-col gap-2 sm:flex">
            <BulkTagBar formId="contacts-bulk" />
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th className="w-6 font-medium">
                      <span className="sr-only">{t("select")}</span>
                    </th>
                    <th>{t("colName")}</th>
                    <th>{t("colKind")}</th>
                    <th>{t("role")}</th>
                    <th>{t("colEmail")}</th>
                    <th>{t("colPhone")}</th>
                    <th>{t("colCity")}</th>
                    <th>{t("colTags")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <input type="checkbox" name="bulk-id" value={c.id} aria-label={t("selectRow", { name: c.display_name })} />
                      </td>
                      <td>
                        <Link href={`/kontakte/${c.id}`} className="font-medium hover:underline">
                          {c.display_name}
                        </Link>
                        {c.blocked ? <span className="ml-2 text-xs text-danger-fg">{t("blocked")}</span> : null}
                        {c.completeness === "incomplete" ? <span className="ml-2 text-xs text-muted">{t("incomplete")}</span> : null}
                      </td>
                      <td>{tl(`kind.${c.kind}`)}</td>
                      <td>
                        <RolePills roles={c.roles} />
                      </td>
                      <td>{c.primary_email ?? ""}</td>
                      <td>{c.primary_phone ?? ""}</td>
                      <td>{c.city ?? ""}</td>
                      <td>{c.tags.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </form>
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
        </>
      )}
    </div>
  );
}
