import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { RuleProposals, type RuleProposal } from "@/components/settings/RuleProposals";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Lern-Workflow (Regel M9-11): offene Regelvorschläge aus wiederholten manuellen
 *  Entscheidungen. Anzeige mit tenant_settings:read, Annehmen und Ablehnen mit
 *  tenant_settings:update (vom Backend geprüft). */
export default async function RuleProposalsPage() {
  const t = await getTranslations("RuleProposals");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const [proposalsRes, settingsRes] = await Promise.all([
    serverFetch("/api/v1/automation/rule-proposals?status=proposed"),
    serverFetch("/api/v1/tenant/settings"),
  ]);
  const proposals = proposalsRes.ok ? ((await proposalsRes.json()) as RuleProposal[]) : [];
  const settings = settingsRes.ok
    ? ((await settingsRes.json()) as { rule_proposal_threshold?: number })
    : {};
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <RuleProposals
        initial={proposals}
        canManage={permissions.includes("tenant_settings:update")}
        initialThreshold={settings.rule_proposal_threshold ?? 5}
      />
    </div>
  );
}
