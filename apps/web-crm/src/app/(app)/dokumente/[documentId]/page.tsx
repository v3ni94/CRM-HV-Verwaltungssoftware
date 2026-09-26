import { getTranslations } from "next-intl/server";

import { PortalReadReceipts, type PortalReadReceiptsOut } from "@/components/documents/PortalReadReceipts";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Document detail (metadata, links, portal read receipts as an indication, A53). Document
 *  reads stay outside the BFF allowlist, therefore everything is read server side. */
export default async function DocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  const t = await getTranslations("DocumentDetail");
  const api = serverApi();
  const { data, error, response } = await api.GET("/api/v1/documents/{document_id}", {
    params: { path: { document_id: documentId } },
  });
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const receiptsResponse = await serverFetch(`/api/v1/documents/${documentId}/portal-read-receipts`);
  const receipts: PortalReadReceiptsOut | null = receiptsResponse.ok ? ((await receiptsResponse.json()) as PortalReadReceiptsOut) : null;
  const contactNames: Record<string, string> = {};
  if (receipts) {
    await Promise.all(
      [...new Set(receipts.items.map((r) => r.contact_id))].map(async (contactId) => {
        const contact = await api.GET("/api/v1/contacts/{contact_id}", { params: { path: { contact_id: contactId } } });
        if (contact.data) contactNames[contactId] = contact.data.display_name;
      }),
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow={t("area")} title={data.title} description={data.filename} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("created")}</p>
          <p className="mt-1 text-sm tabular-nums">{formatDate(data.created_at)}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("mimeType")}</p>
          <p className="mt-1 text-sm">{data.mime_type}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("visibility")}</p>
          <p className="mt-1 text-sm">{data.visibility.length ? data.visibility.map((v) => t(`visibilityValues.${v}`)).join(", ") : t("visibilityNone")}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("links")}</p>
          <p className="mt-1 text-sm">{(data.links ?? []).length ? (data.links ?? []).map((l) => `${l.entity_type} (${l.role})`).join(", ") : t("linksNone")}</p>
        </div>
      </div>
      {receipts ? (
        <PortalReadReceipts data={receipts} contactNames={contactNames} />
      ) : (
        <p role="alert" className={ui.alert}>
          {t("receiptsUnavailable")}
        </p>
      )}
    </div>
  );
}
