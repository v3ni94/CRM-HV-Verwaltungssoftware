import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { ReplyTemplatesAdmin, type ReplyTemplate } from "@/components/settings/ReplyTemplatesAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

/** Antwortvorlagen für Tickets (operator 26.09.2026): Lesen mit tickets:read, Anlegen und
 *  Bearbeiten mit tickets:update oder Administrator (vom Backend geprüft; hier nur die
 *  Anzeige der Aktionen). */
type SearchParams = Record<string, string | undefined>;
type DocumentHit = { id: string; title: string; filename: string };

export default async function ReplyTemplatesPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const t = await getTranslations("ReplyTemplates");
  const params = await searchParams;
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tickets:read")) notFound();
  const canManage = permissions.includes("tickets:update") || permissions.includes("tenant_settings:update");
  const canPickTopic = permissions.includes("members:read");
  const canSearchDocuments = permissions.includes("documents:read");
  const res = await serverFetch("/api/v1/tickets/reply-templates");
  const templates = res.ok ? ((await res.json()) as ReplyTemplate[]) : [];
  // Dokumentsuche für Standardanhänge läuft serverseitig (GET /documents bleibt außerhalb des
  // BFF-Proxys); der Suchbegriff kommt als ?q= und die Treffer gehen als Props an das Formular.
  const q = (params.q ?? "").trim();
  let documentHits: DocumentHit[] | null = null;
  if (canSearchDocuments && q.length >= 2) {
    const search = await serverFetch(`/api/v1/documents?q=${encodeURIComponent(q)}&page_size=10`);
    const page = search.ok ? ((await search.json()) as { items: DocumentHit[] }) : { items: [] };
    documentHits = page.items.map((d) => ({ id: String(d.id), title: String(d.title ?? ""), filename: String(d.filename ?? "") }));
  }
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: "Einstellungen" }]} title={t("title")} description={t("description")} />
      <ReplyTemplatesAdmin
        initialTemplates={templates}
        canManage={canManage}
        canPickTopic={canPickTopic}
        canSearchDocuments={canSearchDocuments}
        documentQuery={q}
        documentHits={documentHits}
      />
    </div>
  );
}
