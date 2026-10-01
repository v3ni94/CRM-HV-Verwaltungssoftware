import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PortalLegalTexts, type LegalTextsConfig } from "@/components/settings/PortalLegalTexts";
import { TextBlocksAdmin, type TextBlock, type TextBlockCode } from "@/components/settings/TextBlocksAdmin";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { PORTAL_LEGAL_CODES } from "@/lib/portal-legal-codes";

export const dynamic = "force-dynamic";

/** Rechtstexte des Portals je Mandant (AE29, M21-04): Impressum, Datenschutzerklärung und
 *  Nutzungsbedingungen als Textbausteine mit Freigabe durch eine zweite Person. Lesen mit
 *  documents:read, Bearbeiten mit documents:update, Freigeben mit documents:approve, Fassung der
 *  Einwilligungsrichtlinie mit contacts:approve (vom Backend geprüft). */
export default async function PortalLegalTextsPage() {
  const t = await getTranslations("PortalLegalTexts");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("documents:read")) notFound();
  const [codesRes, blocksRes, configRes] = await Promise.all([
    serverFetch("/api/v1/document-text-blocks/codes"),
    serverFetch("/api/v1/document-text-blocks"),
    permissions.includes("tenant_settings:read") ? serverFetch("/api/v1/tenant/legal-texts-config") : Promise.resolve(null),
  ]);
  const codes = codesRes.ok
    ? ((await codesRes.json()) as { items: TextBlockCode[] }).items.filter((c) => PORTAL_LEGAL_CODES.includes(c.code))
    : [];
  const blocks = blocksRes.ok
    ? ((await blocksRes.json()) as { items: TextBlock[] }).items.filter((b) => PORTAL_LEGAL_CODES.includes(b.code))
    : [];
  const config = configRes?.ok ? ((await configRes.json()) as LegalTextsConfig) : null;
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/einstellungen", label: t("breadcrumb") }]} title={t("title")} description={t("description")} />
      {config ? <PortalLegalTexts config={config} canChange={permissions.includes("contacts:approve")} /> : null}
      <TextBlocksAdmin
        codes={codes}
        blocks={blocks}
        canEdit={permissions.includes("documents:update")}
        canApprove={permissions.includes("documents:approve")}
      />
    </div>
  );
}
