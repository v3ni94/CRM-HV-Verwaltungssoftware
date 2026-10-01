import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { InvoiceCheckSettingsForm, type InvoiceCheckSettings } from "@/components/accounting/InvoiceCheckSettingsForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

const DEFAULT: InvoiceCheckSettings = { price_tolerance_percent: "0", quantity_tolerance_percent: "0" };

/** Einstellungen, Buchhaltung, Rechnungsprüfung (M14-02, T05-Rest): Toleranzen der sachlichen
 *  Prüfung, `GET/PUT /accounting/invoice-check-settings`. Lesen mit accounting:read, Speichern mit
 *  tenant_settings:update. */
export default async function InvoiceCheckSettingsPage() {
  const t = await getTranslations("InvoiceCheckSettings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("accounting:read")) notFound();
  const res = await serverFetch("/api/v1/accounting/invoice-check-settings");
  const settings = res.ok ? ((await res.json()) as InvoiceCheckSettings) : DEFAULT;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("pageTitle")} description={t("pageDescription")} />
      <InvoiceCheckSettingsForm initial={settings} canUpdate={permissions.includes("tenant_settings:update")} />
    </div>
  );
}
