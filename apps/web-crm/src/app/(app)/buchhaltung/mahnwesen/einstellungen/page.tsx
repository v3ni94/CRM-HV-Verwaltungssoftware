import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DunningScopePicker, type DunningScopeProperty } from "@/components/accounting/DunningScopePicker";
import { DunningSettingsForm, type DunningSettings } from "@/components/accounting/DunningSettingsForm";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const EMPTY_SETTINGS: DunningSettings = {
  levels: [],
  threshold_amount: "0.00",
  fee_from_level: null,
  interest_enabled: false,
  interest_base_rate: null,
  interest_spread: null,
  status: "nicht eingerichtet",
  sources: {},
  own: null,
  tenant_default_exists: false,
};

type Override = { id: string; property_id: string; overridden_fields: string[] };

/** Mandantenweite Mahnstufen oder, mit `?objekt=<id>`, die Überschreibung eines Objekts
 * (Vererbung vom Mandanten, docs/rules/M16-02.md). `GET`, `DELETE` und `.../overrides` sind
 * noch nicht im generierten API-Client (`openapi.json` wird in diesem Durchgang nicht neu
 * erzeugt), daher roher `serverFetch` statt des typisierten `serverApi()`. */
export default async function DunningSettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ objekt?: string }>;
}) {
  const { objekt } = await searchParams;
  const propertyId = objekt || null;
  const t = await getTranslations("Dunning");
  const api = serverApi();
  const me = await getMe();
  redirectIfUnauthenticated(me.response);
  const can = (p: string) => me.data?.permissions.includes(p) ?? false;
  if (!can("accounting:read")) notFound();
  const query = propertyId ? `?property_id=${encodeURIComponent(propertyId)}` : "";
  const [response, overridesResponse, propertiesResult] = await Promise.all([
    serverFetch(`/api/v1/accounting/dunning-settings${query}`),
    serverFetch("/api/v1/accounting/dunning-settings/overrides"),
    api.GET("/api/v1/properties", { params: { query: { page_size: 200 } } }),
  ]);
  redirectIfUnauthenticated(response);
  const settings: DunningSettings = response.ok ? await response.json() : EMPTY_SETTINGS;
  const overrides: Override[] = overridesResponse.ok ? await overridesResponse.json() : [];
  const properties: DunningScopeProperty[] = (propertiesResult.data?.items ?? []).map((p) => ({
    id: String(p.id),
    number: String(p.number),
    name: String(p.name),
  }));
  const byId = new Map(properties.map((p) => [p.id, p]));
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[{ href: "/buchhaltung/mahnwesen", label: t("title") }]}
        title={t("settings")}
      />
      <DunningScopePicker properties={properties} selected={propertyId} />
      <DunningSettingsForm
        key={propertyId ?? "tenant"}
        propertyId={propertyId ?? undefined}
        initial={settings}
        canUpdate={can("accounting:approve")}
      />
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("overridesTitle")}</h2>
        {overrides.length === 0 ? (
          <p className="mt-1 text-sm text-muted">{t("overridesEmpty")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {overrides.map((o) => {
              const p = byId.get(o.property_id);
              return (
                <li key={o.id} className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/buchhaltung/mahnwesen/einstellungen?objekt=${encodeURIComponent(o.property_id)}`}
                    className="hover:underline"
                  >
                    {p ? t("scopeProperty", { number: p.number, name: p.name }) : o.property_id}
                  </Link>
                  <span className="text-muted">
                    {t("overriddenFields", { fields: o.overridden_fields.join(", ") })}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
