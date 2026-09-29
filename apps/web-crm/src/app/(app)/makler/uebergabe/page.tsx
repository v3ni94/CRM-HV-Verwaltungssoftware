import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { HandoverList, type ListParams } from "@/components/handover/HandoverList";
import type { Protocol } from "@/components/handover/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { q?: string; status?: string; art?: string; archiv?: string; datum?: string; von?: string; bis?: string };

/** Übergabeprotokolle (M30) under Makler: search field plus folding filters, chips "Heute"
 *  and "Diese Woche" (server side date filter), cards on phones and a table from `sm`
 *  (M31 WP2). */
export default async function HandoverListPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("Handover");
  const api = serverApi();
  const query = {
    ...(params.q ? { q: params.q } : {}),
    ...(params.status ? { status: params.status } : {}),
    ...(params.art ? { kind: params.art } : {}),
    ...(params.archiv === "1" ? { include_archived: true } : {}),
    ...(params.datum ? { handover_date: params.datum } : {}),
    ...(params.von ? { handover_from: params.von } : {}),
    ...(params.bis ? { handover_to: params.bis } : {}),
    page_size: 100,
  };
  const { data, error, response } = await api.GET("/api/v1/handover/protocols", { params: { query } });
  redirectIfUnauthenticated(response);
  const rows = ((data as { items?: Protocol[] } | undefined)?.items ?? []) as Protocol[];
  const listParams: ListParams = { q: params.q ?? "", status: params.status ?? "", art: params.art ?? "", archiv: params.archiv === "1", datum: params.datum ?? "", von: params.von ?? "", bis: params.bis ?? "" };
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        breadcrumb={[{ href: "/makler", label: t("broker") }]}
        action={
          <Link href="/makler/uebergabe/neu" className={ui.primary}>
            {t("new")}
          </Link>
        }
      />
      {!data ? (
        <>
          <HandoverList rows={[]} params={listParams} />
          <p role="alert" className={ui.alert}>
            {problemMessage(error as Problem | undefined, response.status)}
          </p>
        </>
      ) : (
        <HandoverList rows={rows} params={listParams} />
      )}
    </div>
  );
}
