import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BankSyncSettingsCard } from "@/components/banking/BankSyncSettingsCard";
import { FinApiSettingsCard, type FinApiConfig } from "@/components/banking/FinApiSettingsCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

/** Einstellungen, Bank (M11-finapi): finAPI-Zugangsdaten je Mandant. Nur read only
 *  Kontoinformationsdienst; Zahlungen bleiben über die bestehende Zahlungsfreigabe (G2). */
export default async function BankSettingsPage() {
  const t = await getTranslations("BankSettings");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  if (!me.data?.permissions.includes("tenant_settings:update")) notFound();
  const config = await api.GET("/api/v1/banking/finapi/config");
  const initial = (config.data ?? {
    configured: false,
    base_url: null,
    mandator_id: null,
    sandbox: null,
    auto_fetch_enabled: false,
  }) as FinApiConfig;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("intro")} />
      <p className="text-sm">
        <Link href="/bank" className="font-medium hover:underline">
          {t("setupFinTsLink")}
        </Link>
      </p>
      <FinApiSettingsCard initial={initial} />
      <BankSyncSettingsCard canEdit canRun={me.data.permissions.includes("accounting:update")} />
    </div>
  );
}
