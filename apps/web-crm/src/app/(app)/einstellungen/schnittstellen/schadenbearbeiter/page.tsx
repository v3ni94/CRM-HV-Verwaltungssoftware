import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { SchadenstoolSettings, type SchadenstoolConfig } from "@/components/settings/SchadenstoolSettings";
import { SchadenstoolTakeover } from "@/components/settings/SchadenstoolTakeover";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

const EMPTY: SchadenstoolConfig = {
  base_url: null,
  enabled: false,
  token_set: false,
  token_last4: null,
  token_invalid: false,
  hmac_secret_set: false,
  webhook_secret_set: false,
  webhook_path: "",
  avv_confirmed_on: null,
  avv_confirmed_by: null,
  avv_note: null,
  last_tested_at: null,
  last_test_ok: null,
  last_test_message: null,
  last_pull_at: null,
  last_pull_message: null,
};

/** Einstellungen, Schadenbearbeiter (INT-SDT-01): connection with AVV confirmation, and the
 *  takeover queue of existing damage tickets. Read with tenant_settings:read, change with
 *  tenant_settings:update, decide the takeover with tickets:create. */
export default async function SchadenstoolSettingsPage() {
  const t = await getTranslations("Schadenstool");
  const ts = await getTranslations("Settings");
  const tm = await getTranslations("Metering");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const res = await serverFetch("/api/v1/integrations/schadenstool/config");
  const initial: SchadenstoolConfig = res.ok ? ((await res.json()) as SchadenstoolConfig) : EMPTY;
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
      <SchadenstoolSettings initial={initial} canManage={permissions.includes("tenant_settings:update")} />
      {initial.enabled && permissions.includes("tickets:create") ? <SchadenstoolTakeover canDecide /> : null}
    </div>
  );
}
