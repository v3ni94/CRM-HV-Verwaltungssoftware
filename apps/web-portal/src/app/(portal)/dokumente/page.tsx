import { getFormatter, getTranslations } from "next-intl/server";

import type { PortalDocument } from "@/components/portal/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Freigegebene Dokumente (M21): list plus download through /api/portal-files (binary, same
 *  access check as the API's /portal/documents/{id}/download). */
export default async function DocumentsPage() {
  const [t, format] = await Promise.all([getTranslations("Documents"), getFormatter()]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/documents");
  redirectIfUnauthenticated(response);
  if (!data) throw new Error(String(error));
  const rows = data as unknown as PortalDocument[];
  return (
    <div className={ui.pageGap}>
      <h1 className={ui.title}>{t("title")}</h1>
      {rows.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2`}>
            <span className="flex flex-col gap-0.5">
              <span className="font-medium">{row.title}</span>
              <span className="text-xs text-subtle">
                {t("created")}{" "}
                {format.dateTime(new Date(row.created_at), { day: "2-digit", month: "2-digit", year: "numeric" })}
              </span>
            </span>
            <a
              href={`/api/portal-files/portal/documents/${row.id}/download`}
              className={ui.buttonSm}
              download={row.filename}
            >
              {t("download")}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
