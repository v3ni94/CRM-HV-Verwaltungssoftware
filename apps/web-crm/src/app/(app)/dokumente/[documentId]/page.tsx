import { getTranslations } from "next-intl/server";

import { DocumentRedactions, type Redaction } from "@/components/documents/DocumentRedactions";
import { DocumentVisibilityEditor } from "@/components/documents/DocumentVisibilityEditor";
import { PortalReadReceipts, type PortalReadReceiptsOut } from "@/components/documents/PortalReadReceipts";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Filing = {
  routed: boolean;
  status?: "pending" | "submitted" | "done" | "failed";
  category?: string | null;
  subfolder?: string | null;
  drive_url?: string | null;
  paperless_id?: number | null;
  last_error?: string | null;
};

/** Document detail (metadata, links, portal read receipts as an indication, A53). Document
 *  reads stay outside the BFF allowlist, therefore everything is read server side. */
export default async function DocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = await params;
  const t = await getTranslations("DocumentDetail");
  const api = serverApi();
  const me = await getMe();
  // Freigabeflag (M21-03) nur mit dem Recht, das die API für PATCH /documents verlangt.
  const canEditVisibility = me.data?.permissions.includes("documents:update") ?? false;
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
  // Ablage über objektakte (Upload 26.09.2026): Stand, Drive-Link und Paperless-ID, falls geroutet.
  const filingResponse = await serverFetch(`/api/v1/integrations/objektakte/documents/${documentId}/filing`);
  const filing: Filing | null = filingResponse.ok ? ((await filingResponse.json()) as Filing) : null;
  const receiptsResponse = await serverFetch(`/api/v1/documents/${documentId}/portal-read-receipts`);
  const receipts: PortalReadReceiptsOut | null = receiptsResponse.ok ? ((await receiptsResponse.json()) as PortalReadReceiptsOut) : null;
  // Geschwärzte Kopien (Q03-03): Liste am Original; eine Kopie ist selbst kein Original.
  const redactionsResponse = await serverFetch(`/api/v1/documents/${documentId}/redactions`);
  const redactions: Redaction[] = redactionsResponse.ok ? ((await redactionsResponse.json()) as Redaction[]) : [];
  const isRedactedCopy = !redactionsResponse.ok ? false : data.links?.some((l) => l.entity_type === "document" && l.role === "generated") ?? false;
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
          <DocumentVisibilityEditor documentId={documentId} visibility={data.visibility} canEdit={canEditVisibility} />
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("links")}</p>
          <p className="mt-1 text-sm">{(data.links ?? []).length ? (data.links ?? []).map((l) => `${l.entity_type} (${l.role})`).join(", ") : t("linksNone")}</p>
        </div>
      </div>
      {filing?.routed ? (
        <div className={ui.card} data-testid="document-filing">
          <p className={ui.subtitle}>{t("filing.title")}</p>
          <p className="mt-1 text-sm">
            {t(`filing.status.${filing.status ?? "pending"}`)}
            {filing.category ? ` · ${filing.category}${filing.subfolder ? ` / ${filing.subfolder}` : ""}` : ""}
          </p>
          {filing.last_error ? <p className="mt-1 text-xs text-danger-fg">{filing.last_error}</p> : null}
          <div className="mt-2 flex flex-wrap gap-2">
            {filing.drive_url ? (
              <a href={filing.drive_url} target="_blank" rel="noreferrer" className={ui.buttonSm}>
                {t("filing.drive")}
              </a>
            ) : null}
            {filing.paperless_id ? (
              <a href={`/api/bff/dms-documents/${String(filing.paperless_id)}/file?kind=preview`} className={ui.buttonSm}>
                {t("filing.paperless")}
              </a>
            ) : null}
          </div>
        </div>
      ) : null}
      {redactionsResponse.ok && !isRedactedCopy ? (
        <DocumentRedactions
          documentId={documentId}
          initial={redactions}
          userId={me.data?.user_id ?? null}
          canCreate={me.data?.permissions.includes("documents:update") ?? false}
          canApprove={me.data?.permissions.includes("documents:approve") ?? false}
        />
      ) : null}
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
