import { getFormatter, getTranslations } from "next-intl/server";

import Link from "next/link";

import { DocumentList } from "@/components/portal/DocumentList";
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

/** Freigegebene Dokumente (M21): list plus download through /api/portal-files (binary, same
 *  access check as the API's /portal/documents/{id}/download). Search and the expandable
 *  details (read receipt "opened" via the BFF) are client side in DocumentList. */
export default async function DocumentsPage() {
  const [t, format] = await Promise.all([getTranslations("Documents"), getFormatter()]);
  const { data, error, response } = await serverApi().GET("/api/v1/portal/documents");
  await redirectIfUnauthenticated(response);
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
      <DocumentList documents={rows} />
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
