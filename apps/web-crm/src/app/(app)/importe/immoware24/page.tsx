import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { Immoware24Wizard } from "@/components/imports/Immoware24Wizard";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

const OVERVIEW = ["properties", "units", "contacts", "contracts"] as const;

export default async function Immoware24Page() {
  const t = await getTranslations("Immoware24");
  const api = serverApi();
  const [fields, mappings, overview, me] = await Promise.all([
    api.GET("/api/v1/imports/immoware24/fields"),
    api.GET("/api/v1/imports/immoware24/mappings"),
    api.GET("/api/v1/imports/immoware24/overview"),
    api.GET("/api/v1/auth/me"),
  ]);
  redirectIfUnauthenticated(fields.response);
  const canUndo = me.data?.permissions.includes("ai:delete") ?? false;
  return (
    <div className="flex flex-col gap-4">
      <Link href="/importe" className="text-sm text-muted hover:underline">
        {t("backToImports")}
      </Link>
      <PageHeader title={t("title")} />
      <p className="text-sm text-muted">{t("intro")}</p>
      {overview.data ? (
        <section className={ui.card} aria-labelledby="overview-title">
          <h2 id="overview-title" className="mb-2 text-sm font-semibold">
            {t("overviewTitle")}
          </h2>
          <dl className="flex flex-wrap gap-6 text-sm">
            {OVERVIEW.map((key) => (
              <div key={key} className="flex flex-col">
                <dt className="text-xs text-muted">{t(`overview.${key}`)}</dt>
                <dd className="font-semibold">{overview.data[key] ?? 0}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}
      {!fields.data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(fields.error as Problem | undefined, fields.response.status)}
        </p>
      ) : (
        <Immoware24Wizard fields={fields.data} mappings={mappings.data ?? []} canUndo={canUndo} />
      )}
      <Link href="/importe/immoware24-listen" className="text-sm font-medium hover:underline">
        {t("listImportLink")}
      </Link>
    </div>
  );
}
