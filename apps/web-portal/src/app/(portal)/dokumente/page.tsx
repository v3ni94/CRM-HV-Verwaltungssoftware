import { getFormatter, getTranslations } from "next-intl/server";

import Link from "next/link";

import { DocumentBundleList } from "@/components/portal/DocumentBundleList";
import type { PortalDocument } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { ui } from "@/lib/ui";

type StaffHandover = {
  id: string;
  number: string;
  status: string;
  address: string;
  handover_date: string | null;
};

export const dynamic = "force-dynamic";

const SORTS = ["created_desc", "created_asc", "title_asc", "title_desc"];

/** Freigegebene Dokumente (M21): list plus download through /api/portal-files (binary, same
 *  access check as the API's /portal/documents/{id}/download). */
export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; sort?: string }>;
}) {
  const [t, format] = await Promise.all([getTranslations("Documents"), getFormatter()]);
  const params = await searchParams;
  const q = (params.q ?? "").slice(0, 100);
  const sort = SORTS.includes(params.sort ?? "") ? (params.sort as string) : "created_desc";
  // M25-06: search and sort run in the API, inside the documents this account may see.
  const { data, error, response } = await serverApi().GET("/api/v1/portal/documents", {
    params: { query: { q: q || undefined, sort } },
  } as never);
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as PortalDocument[];
  // Staff with the portal permission "handover:read" (M2-08) additionally see the handover
  // protocols of their objects; any other status (403 for external users) hides the list.
  const handoverResponse = await serverFetch("/api/v1/portal/handovers");
  const handovers =
    handoverResponse.status === 200 ? ((await handoverResponse.json()) as StaffHandover[]) : null;
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      <form method="get" className="flex flex-wrap items-end gap-3" role="search">
        <label className="flex flex-col gap-1 text-sm">
          {t("search")}
          <input name="q" type="search" defaultValue={q} placeholder={t("searchPlaceholder")} className={ui.input} maxLength={100} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("sort")}
          <select name="sort" defaultValue={sort} className={ui.input}>
            <option value="created_desc">{t("sortCreatedDesc")}</option>
            <option value="created_asc">{t("sortCreatedAsc")}</option>
            <option value="title_asc">{t("sortTitleAsc")}</option>
            <option value="title_desc">{t("sortTitleDesc")}</option>
          </select>
        </label>
        <button type="submit" className={ui.buttonSm}>
          {t("apply")}
        </button>
      </form>
      {rows.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      {rows.length > 0 ? <p className="text-xs text-subtle">{t("readNote")}</p> : null}
      {rows.length > 0 ? (
        <DocumentBundleList
          rows={rows}
          formatDate={(value) =>
            format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" })
          }
        />
      ) : null}
      {handovers ? (
        <section className={ui.pageGap}>
          <h2 className="text-lg font-semibold">{t("handoversTitle")}</h2>
          {handovers.length === 0 ? <p className={ui.notice}>{t("handoversEmpty")}</p> : null}
          <ul className="flex flex-col gap-3">
            {handovers.map((row) => (
              <li key={row.id}>
                <Link href={`/uebergabe/${row.id}`} className={`${ui.cardLink} flex flex-col gap-0.5`}>
                  <span className="font-medium">{row.number}</span>
                  <span className="text-sm text-muted">{row.address}</span>
                  {row.handover_date ? (
                    <span className="text-xs text-subtle">
                      {t("handoverDate")}{" "}
                      {format.dateTime(new Date(row.handover_date), { day: "2-digit", month: "2-digit", year: "numeric" })}
                    </span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
