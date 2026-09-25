import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

export const dynamic = "force-dynamic";

export default async function HoaPage() {
  const t = await getTranslations("Hoa");
  const { data, error, response } = await serverApi().GET("/api/v1/properties", {
    params: { query: { page_size: 200 } },
  });
  redirectIfUnauthenticated(response);
  const rows = (data?.items ?? []).filter((p) => p.management_type !== "rental");
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <p className={ui.notice}>{t("gateNotice")}</p>
      <div className={`${ui.card} flex flex-wrap items-center justify-between gap-3`}>
        <p className="text-sm text-muted">{t("objectsHint")}</p>
        <Link href="/objekte?art=hoa" className="shrink-0 text-sm font-medium text-gold hover:underline">
          {t("objectsLink")} →
        </Link>
      </div>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((p) => (
            <li key={p.id}>
              <Link href={`/weg/${p.id}`} className="font-medium hover:underline">
                {p.number} {p.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
