import { getTranslations } from "next-intl/server";

import { redirectIfUnauthenticated, serverGet } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import type { PortalDocument } from "@/lib/portal";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const t = await getTranslations("Documents");
  const { data: docs, response } = await serverGet<PortalDocument[]>("/api/v1/portal/documents");
  redirectIfUnauthenticated(response);
  return (
    <div className="flex flex-col gap-5">
      <h1 className={ui.title}>{t("title")}</h1>
      {!docs || docs.length === 0 ? (
        <p className={ui.notice}>{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-bg shadow-card">
          <table className={ui.table}>
            <thead>
              <tr>
                <th scope="col">{t("colTitle")}</th>
                <th scope="col">{t("colFile")}</th>
                <th scope="col">{t("colDate")}</th>
                <th scope="col" className="sr-only">
                  {t("download")}
                </th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id}>
                  <td className="font-medium text-fg">{doc.title}</td>
                  <td className="text-muted">{doc.filename}</td>
                  <td className="text-muted">{formatDate(doc.created_at)}</td>
                  <td>
                    <a href={`/api/bff/portal/documents/${doc.id}/download`} className={ui.buttonSm} download>
                      {t("download")}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
