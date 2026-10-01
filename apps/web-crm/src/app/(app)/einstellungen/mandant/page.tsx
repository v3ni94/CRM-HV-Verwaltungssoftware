import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { CircularLowerMajoritySwitch } from "@/components/settings/CircularLowerMajoritySwitch";
import { CompanySettings } from "@/components/settings/CompanySettings";
import { SignatureTemplateSettings, type SignatureTemplate } from "@/components/settings/SignatureTemplateSettings";
import { BillingSettingsForm, type BillingSettings } from "@/components/settings/BillingSettings";
import { ManagerEntitySetup, type ManagerEntityStatus } from "@/components/settings/ManagerEntitySetup";
import { AiLearningExamples } from "@/components/settings/AiLearningExamples";
import { ResolutionKindsSettings } from "@/components/settings/ResolutionKindsSettings";
import { ConsumptionInfoSwitch, type ConsumptionInfoSettings } from "@/components/settings/ConsumptionInfoSwitch";
import { HandoverOfflineSwitch } from "@/components/settings/HandoverOfflineSwitch";
import { MeteringModuleSwitch } from "@/components/settings/MeteringModuleSwitch";
import { GMAIL_DONE_SYNC_DEFAULTS, GmailDoneSync, type GmailDoneSyncSettings } from "@/components/settings/GmailDoneSync";
import { InspectionPackageDefaultDays } from "@/components/settings/InspectionPackageDefaultDays";
import { PortalSettings, type PortalSecondFactor } from "@/components/settings/PortalSettings";
import { TicketReopenWindow } from "@/components/settings/TicketReopenWindow";
import { TicketReplyApprovalAll } from "@/components/settings/TicketReplyApprovalAll";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";
import { PageHeader } from "@/components/ui/PageHeader";

export const dynamic = "force-dynamic";

export default async function CompanySettingsPage() {
  const t = await getTranslations("CompanySettings");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("tenant_settings:read")) notFound();
  const settings = await api.GET("/api/v1/tenant/settings");
  if (!settings.data) return <p role="alert" className={ui.alert}>{t("loadError")}</p>;
  const billingRes = await serverFetch("/api/v1/tenant/billing-settings");
  const billingData: BillingSettings | null = billingRes.ok ? await billingRes.json() : null;
  const tb = await getTranslations("BillingSettings");
  const managerRes = await serverFetch("/api/v1/tenant/manager-entity");
  const managerData: ManagerEntityStatus | null = managerRes.ok ? await managerRes.json() : null;
  const circularRes = await serverFetch("/api/v1/hoa/circular-lower-majority");
  const circularData: { enabled: boolean } | null = circularRes.ok ? await circularRes.json() : null;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} />
      <CompanySettings initial={settings.data.company} branding={settings.data.branding} canUpdate={can("tenant_settings:update")} />
      <PortalSettings
        branding={settings.data.branding as Record<string, unknown>}
        secondFactor={((settings.data as { portal_second_factor?: PortalSecondFactor }).portal_second_factor ?? "account_choice")}
        canUpdate={can("tenant_settings:update")}
      />
      <ManagerEntitySetup initial={managerData} canUpdate={can("tenant_settings:update")} />
      <SignatureTemplateSettings
        initial={((settings.data as { signature_template?: SignatureTemplate }).signature_template ?? { text: null, html: null, logo_url: null })}
        canUpdate={can("tenant_settings:update")}
      />
      <TicketReplyApprovalAll initial={settings.data.ticket_reply_approval_all} canUpdate={can("tenant_settings:update")} />
      <TicketReopenWindow
        initial={settings.data.ticket_reopen_window_days ?? 30}
        canUpdate={can("tenant_settings:update")}
      />
      <InspectionPackageDefaultDays
        initial={(settings.data as { inspection_package_default_days?: number | null }).inspection_package_default_days ?? null}
        canUpdate={can("tenant_settings:update")}
      />
      <GmailDoneSync
        initial={{ ...GMAIL_DONE_SYNC_DEFAULTS, ...(settings.data as Partial<GmailDoneSyncSettings>) }}
        version={settings.data.version}
        canUpdate={can("tenant_settings:update")}
      />
      <MeteringModuleSwitch initial={settings.data.metering_module_enabled ?? false} canUpdate={can("tenant_settings:update")} />
      <HandoverOfflineSwitch initial={Boolean((settings.data as { handover_offline_enabled?: boolean }).handover_offline_enabled)} canUpdate={can("tenant_settings:update")} />
      <ConsumptionInfoSwitch
        initial={{
          consumption_info_enabled: false,
          consumption_info_notifications_enabled: false,
          consumption_info_template_verified: false,
          ...(settings.data as Partial<ConsumptionInfoSettings>),
        }}
        canUpdate={can("tenant_settings:update")}
      />
      <AiLearningExamples
        initial={settings.data.ai_learning_examples_enabled ?? false}
        initialRetentionMonths={settings.data.ai_learning_examples_retention_months ?? 24}
        canUpdate={can("tenant_settings:update")}
      />
      <ResolutionKindsSettings
        initial={{
          disabled: settings.data.resolution_kinds?.disabled ?? [],
          custom: settings.data.resolution_kinds?.custom ?? [],
        }}
        canUpdate={can("tenant_settings:update")}
      />
      <CircularLowerMajoritySwitch initial={circularData?.enabled ?? false} canUpdate={can("tenant_settings:update")} />
      <section className="flex flex-col gap-2">
        <h2 id="billing-settings-title" className="text-lg font-semibold">{tb("title")}</h2>
        {billingData ? (
          <BillingSettingsForm initial={billingData} canUpdate={can("tenant_settings:update")} />
        ) : (
          <p role="alert" className={ui.alert}>{tb("loadError")}</p>
        )}
      </section>
    </div>
  );
}
