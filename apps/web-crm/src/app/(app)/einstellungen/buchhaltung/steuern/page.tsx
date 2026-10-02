import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  TaxSettingsAdmin,
  type ContactOption,
  type PropertyOption,
  type RoleOption,
  type TaxSettings,
} from "@/components/settings/TaxSettingsAdmin";
import { ReceivableRulesSettings, type ReceivableRules } from "@/components/settings/ReceivableRulesSettings";
import { Section35aCertificate } from "@/components/accounting/Section35aCertificate";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";

export const dynamic = "force-dynamic";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  const res = await serverFetch(path);
  if (!res.ok) return fallback;
  return (await res.json()) as T;
}

const EMPTY: TaxSettings = {
  input_tax_enabled: false,
  input_tax_account_number: null,
  construction_withholding_enabled: false,
  construction_withholding_percent: "15.00",
  section_35a_enabled: false,
  approval_limits_enabled: false,
  approval_limits: [],
};

/** Einstellungen, Buchhaltung, Steuern (M14-02, M14-03, M14-04): Schalter je Mandant (Standard
 *  aus), Vorsteuerkonto, Bauabzugsteuer-Satz als Entwurfswert, Freigabegrenzen je Rolle,
 *  Umsatzsteueroption je Objekt und Steuerkennzeichen je Lieferant. Schalter nur mit
 *  tenant_settings:update, Profile mit accounting:update. Alles Entwurf, zu prüfen durch
 *  Steuerberater. */
export default async function TaxSettingsPage() {
  const t = await getTranslations("TaxSettings");
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const permissions = me.data?.permissions ?? [];
  if (!permissions.includes("tenant_settings:read")) notFound();
  const api = serverApi();
  const [settings, roles, properties, contacts, tenantSettings] = await Promise.all([
    getJson<TaxSettings>("/api/v1/accounting/tax/settings", EMPTY),
    getJson<RoleOption[]>("/api/v1/tenant/roles", []),
    getJson<{ items: PropertyOption[] }>("/api/v1/properties?page_size=200", { items: [] }),
    getJson<{ items: ContactOption[] }>("/api/v1/contacts?kind=company&page_size=200", { items: [] }),
    api.GET("/api/v1/tenant/settings"),
  ]);
  // `payment_interval` (M13-01a) is not yet in the generated api-client types until the next
  // `make openapi` (run centrally); the backend already returns it, so the fallback merge below
  // keeps this page building without a stale-type mismatch.
  const receivableRules: ReceivableRules = {
    enabled: false,
    proration_method: "calendar_days",
    vat_enabled: false,
    payment_interval: null,
    ...(tenantSettings.data?.receivable_rules ?? {}),
  };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} />
      <ReceivableRulesSettings initial={receivableRules} canUpdate={permissions.includes("tenant_settings:update")} />
      <TaxSettingsAdmin
        initial={settings}
        roles={(Array.isArray(roles) ? roles : []).map((r) => ({ code: r.code, name: r.name }))}
        properties={(properties.items ?? []).map((p) => ({ id: p.id, number: p.number, name: p.name }))}
        contacts={(contacts.items ?? []).map((c) => ({ id: c.id, display_name: c.display_name }))}
        canManageSettings={permissions.includes("tenant_settings:update")}
        canManageProfiles={permissions.includes("accounting:update")}
      />
      {permissions.includes("accounting:read") ? <Section35aCertificate /> : null}
    </div>
  );
}
