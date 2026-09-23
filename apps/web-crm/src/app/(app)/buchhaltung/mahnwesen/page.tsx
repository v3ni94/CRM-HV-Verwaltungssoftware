import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { DunningPreviewButton } from "@/components/accounting/DunningPreviewButton";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function DunningPage() {
  const t = await getTranslations("Dunning");
  const { data, response } = await serverApi().GET("/api/v1/accounting/dunning-runs");
  redirectIfUnauthenticated(response);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("title")}</h1>
      <p className={ui.notice}>{t("notice")}</p>
      <DunningPreviewButton today={today} />
      <h2 className="font-medium">{t("runs")}</h2>
      {(data ?? []).length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {(data ?? []).map((r) => (
            <li key={String(r.id)}>
              <Link href={`/buchhaltung/mahnwesen/${String(r.id)}`} className="hover:underline">
                {formatDate(String(r.run_date))} · {t(`runStatus.${String(r.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
