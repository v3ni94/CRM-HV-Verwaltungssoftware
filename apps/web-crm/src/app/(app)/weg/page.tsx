import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { PropertyList } from "@/components/properties/PropertyList";

export const dynamic = "force-dynamic";

/** WEG list in the same layout as the rental and SEV lists (operator 01.10.2026): search,
 *  PropertyList cards and table; rows open the HOA management of the property. */
export default async function HoaPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const t = await getTranslations("Hoa");
  const tp = await getTranslations("Properties");
  const { data, error, response } = await serverApi().GET("/api/v1/properties", {
    params: { query: { page_size: 200, ...(q ? { q } : {}) } },
  });
  redirectIfUnauthenticated(response);
  const rows = (data?.items ?? []).filter((p) => p.management_type !== "rental");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageHeader eyebrow={tp("area")} title={t("title")} />
        <form className="flex gap-2" role="search" aria-label={tp("search")}>
          <input className={ui.input} name="q" defaultValue={q ?? ""} placeholder={tp("searchPlaceholder")} aria-label={tp("search")} />
          <button type="submit" className={ui.button}>
            {tp("search")}
          </button>
        </form>
      </div>
      <p className={ui.notice}>{t("gateNotice")}</p>
      <p className="text-sm text-muted">
        {t("objectsHint")}{" "}
        <Link href="/objekte?art=hoa" className="font-medium text-accent-strong hover:underline">
          {t("objectsLink")}
        </Link>
      </p>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <PropertyList rows={rows} detailBase="/weg" />
      )}
    </div>
  );
}
