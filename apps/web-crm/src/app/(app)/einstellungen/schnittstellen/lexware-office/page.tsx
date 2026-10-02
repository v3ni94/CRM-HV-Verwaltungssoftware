import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { LexofficeSettings, type LexofficeConfig, type LexofficeKindMapping, type LexofficeLegalEntity, type LexofficeMailbox } from "@/components/settings/LexofficeSettings";
import { LexofficeRuns } from "@/components/settings/LexofficeRuns";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

async function load<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  return res.ok ? ((await res.json()) as T) : fallback;
}

/** Einstellungen, Lexware Office (INT-LEXO-01): one organisation per legal entity with API
 *  key (write only), AVV, switches and connection test; invoice kind mapping; contact links;
 *  queue; recurring invoice preparations. Read with tenant_settings:read. */
export default async function LexofficeSettingsPage() {
  const t = await getTranslations("Lexoffice");
  const ts = await getTranslations("Settings");
  const tm = await getTranslations("Metering");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const [configs, entities, kinds, mailboxes] = await Promise.all([
    load<LexofficeConfig[]>("/api/v1/integrations/lexoffice/configs", []),
    load<LexofficeLegalEntity[]>("/api/v1/integrations/lexoffice/legal-entities", []),
    load<LexofficeKindMapping[]>("/api/v1/integrations/lexoffice/invoice-kinds", []),
    load<LexofficeMailbox[]>("/api/v1/mail/mailboxes", []),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[
          { href: "/einstellungen", label: ts("title") },
          { href: "/einstellungen/schnittstellen", label: tm("interfaces") },
          { label: t("title") },
        ]}
        title={t("title")}
        description={t("pageIntro")}
      />
      <LexofficeSettings
        configs={configs}
        legalEntities={entities}
        kinds={kinds}
        mailboxes={mailboxes}
        canManage={permissions.includes("tenant_settings:update")}
        canLinkContacts={permissions.includes("contacts:update")}
        canAccounting={permissions.includes("accounting:create")}
      />
      <LexofficeRuns canImport={permissions.includes("accounting:create")} />
    </div>
  );
}
