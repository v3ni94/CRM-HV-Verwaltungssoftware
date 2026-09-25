import { getFormatter, getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Listed } from "@/components/handover/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function HandoverListPage() {
  const [t, format] = await Promise.all([getTranslations("Handover"), getFormatter()]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/handover");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as Listed[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {rows.length === 0 ? <p className={ui.notice}>{t("access.none")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id}>
            <Link href={`/uebergabe/${row.id}`} className={`${ui.cardLink} flex flex-col gap-1`}>
              <span className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">
                  {row.number}
                  {row.version > 1 ? ` V${row.version}` : ""}
                </span>
                <span className={row.locked ? ui.badge : ui.badgeGold}>
                  {t(`statusLabel.${row.status}`)}
                </span>
              </span>
              <span className="text-sm text-muted">{row.address || t("list.object")}</span>
              <span className="text-xs text-subtle">
                {row.handover_date
                  ? `${t("list.date")} ${format.dateTime(new Date(row.handover_date), { day: "2-digit", month: "2-digit", year: "numeric" })}`
                  : null}
                {row.right === "read" && row.valid_to
                  ? ` · ${t("access.read", { date: format.dateTime(new Date(row.valid_to), { day: "2-digit", month: "2-digit", year: "numeric" }) })}`
                  : row.right === "edit"
                    ? ` · ${t("access.edit")}`
                    : null}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
