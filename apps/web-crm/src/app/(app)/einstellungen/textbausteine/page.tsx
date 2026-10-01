import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { TextBlocksAdmin, type TextBlock, type TextBlockCode } from "@/components/settings/TextBlocksAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PORTAL_LEGAL_CODES } from "@/lib/portal-legal-codes";

export const dynamic = "force-dynamic";

/** Textbausteine mit Freigabe (AE16, AA11-01/02): Lesen mit documents:read, Bearbeiten mit
 *  documents:update, Freigeben mit documents:approve (vom Backend geprüft). */
export default async function TextBlocksPage() {
  const t = await getTranslations("TextBlocks");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("documents:read")) notFound();
  const [codesRes, blocksRes] = await Promise.all([
    serverFetch("/api/v1/document-text-blocks/codes"),
    serverFetch("/api/v1/document-text-blocks"),
  ]);
  // The portal legal texts (AE29) have their own page /einstellungen/portal-rechtstexte.
  const codes = codesRes.ok
    ? ((await codesRes.json()) as { items: TextBlockCode[] }).items.filter((c) => !PORTAL_LEGAL_CODES.includes(c.code))
    : [];
  const blocks = blocksRes.ok
    ? ((await blocksRes.json()) as { items: TextBlock[] }).items.filter((b) => !PORTAL_LEGAL_CODES.includes(b.code))
    : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: "Einstellungen" }]} title={t("title")} description={t("description")} />
      <TextBlocksAdmin
        codes={codes}
        blocks={blocks}
        canEdit={permissions.includes("documents:update")}
        canApprove={permissions.includes("documents:approve")}
      />
    </div>
  );
}
