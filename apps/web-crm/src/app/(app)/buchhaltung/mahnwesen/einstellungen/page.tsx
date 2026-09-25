import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { DunningSettingsForm, type DunningSettings } from "@/components/accounting/DunningSettingsForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";

export const dynamic = "force-dynamic";

const EMPTY_SETTINGS: DunningSettings = {
  levels: [],
  threshold_amount: "0.00",
  fee_from_level: null,
  interest_enabled: false,
  interest_base_rate: null,
  interest_spread: null,
  status: "nicht eingerichtet",
};

/** Mandantenweite Mahnstufen (Objekt-Override folgt demselben Endpunkt mit `property_id`,
 * hier zunächst die Mandanteneinstellung, siehe docs/rules/M16-01.md). `GET` und `POST
 * .../presets` sind neu (M16, 25.09.2026) und noch nicht im generierten API-Client
 * (`openapi.json` wird in diesem Durchgang nicht neu erzeugt), daher roher `serverFetch`
 * statt des typisierten `serverApi()`. */
export default async function DunningSettingsPage() {
  const t = await getTranslations("Dunning");
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("accounting:read")) notFound();
  const response = await serverFetch("/api/v1/accounting/dunning-settings");
  redirectIfUnauthenticated(response);
  const settings: DunningSettings = response.ok ? await response.json() : EMPTY_SETTINGS;
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung/mahnwesen", label: t("title") }]}
        title={t("settings")}
      />
      <DunningSettingsForm initial={settings} canUpdate={can("accounting:approve")} />
    </div>
  );
}
