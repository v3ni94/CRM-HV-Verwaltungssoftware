import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DunningPreviewButton } from "@/components/accounting/DunningPreviewButton";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const RUN_VARIANT: Record<string, StatusPillVariant> = {
  preview: "warning",
  approved: "success",
};

export default async function DunningPage() {
  const t = await getTranslations("Dunning");
  const { data, response } = await serverApi().GET("/api/v1/accounting/dunning-runs");
  redirectIfUnauthenticated(response);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("title")}
        action={
          <Link href="/buchhaltung/mahnwesen/einstellungen" className={ui.secondary}>
            {t("settings")}
          </Link>
        }
      />
      <p className={ui.notice}>{t("notice")}</p>
      <DunningPreviewButton today={today} />
      <h2 className={ui.h2}>{t("runs")}</h2>
      {(data ?? []).length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {(data ?? []).map((r) => (
            <li key={String(r.id)} className="flex items-center gap-2">
              <Link href={`/buchhaltung/mahnwesen/${String(r.id)}`} className="hover:underline">
                {formatDate(String(r.run_date))}
              </Link>
              <StatusPill variant={RUN_VARIANT[String(r.status)] ?? "neutral"} label={t(`runStatus.${String(r.status)}`)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
