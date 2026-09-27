import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AuditLogPanel } from "@/components/common/AuditLogPanel";
import { EntityLinksBar, type EntityLink } from "@/components/common/EntityLinksBar";
import { Prospects } from "@/components/letting/Prospects";
import { EnergyCertificateForm, type EnergyBuilding } from "@/components/properties/EnergyCertificateForm";
import { UnitDetails } from "@/components/properties/UnitDetails";
import { UnitMasterData, type UnitMaster } from "@/components/properties/UnitMasterData";
import { MeterChangesPanel, VacancyValuesPanel, type MeterChangeRow, type VacancyValueRow } from "@/components/properties/UnitPanels";
import { TicketsSection, type TicketSummary } from "@/components/tickets/TicketsSection";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

async function load<T>(path: string, fallback: T): Promise<T> {
  const response = await serverFetch(path);
  return response.ok ? ((await response.json()) as T) : fallback;
}

type MeterRow = { id: string; unit_id: string | null; number: string; meter_type_code: string };

export default async function LettingUnitPage({ params }: { params: Promise<{ unitId: string }> }) {
  const { unitId } = await params;
  const [t, tp, tu] = await Promise.all([
    getTranslations("Prospects"),
    getTranslations("Properties"),
    getTranslations("Units"),
  ]);
  const api = serverApi();
  const unitPath = { params: { path: { unit_id: unitId } } };
  const [unit, occupants, expose, prospects, tickets] = await Promise.all([
    api.GET("/api/v1/units/{unit_id}", unitPath),
    api.GET("/api/v1/units/{unit_id}/occupants", unitPath),
    api.GET("/api/v1/letting/units/{unit_id}/expose", unitPath),
    api.GET("/api/v1/letting/prospects", { params: { query: { unit_id: unitId } } }),
    api.GET("/api/v1/tickets", { params: { query: { unit_id: unitId, limit: 50, include_closed: true } } }),
  ]);
  redirectIfUnauthenticated(unit.response);
  if (!unit.data) return <p role="alert" className={ui.alert}>{problemMessage(unit.error as Problem | undefined, unit.response.status)}</p>;
  if (!expose.data) return <p role="alert" className={ui.alert}>{problemMessage(expose.error as Problem | undefined, expose.response.status)}</p>;
  const propertyId = unit.data.property_id;
  const [property, building, me, subCommunities, vacancyValues, meters, ledgers] = await Promise.all([
    api.GET("/api/v1/properties/{property_id}", { params: { path: { property_id: propertyId } } }),
    api.GET("/api/v1/buildings/{building_id}", { params: { path: { building_id: unit.data.building_id } } }),
    getMe(),
    load<{ id: string; code: string; name: string }[]>(`/api/v1/properties/${propertyId}/sub-communities`, []),
    load<VacancyValueRow[]>(`/api/v1/units/${unitId}/vacancy-allocation-values`, []),
    load<MeterRow[]>(`/api/v1/properties/${propertyId}/meters`, []),
    load<{ id: string }[]>(`/api/v1/ledgers?property_id=${propertyId}`, []),
  ]);
  const unitMeters = meters.filter((m) => m.unit_id === unitId);
  const meterChanges = (
    await Promise.all(
      unitMeters.map(async (m) =>
        (await load<MeterChangeRow[]>(`/api/v1/meters/${m.id}/changes`, [])).map((c) => ({ ...c, meter_label: `${m.meter_type_code} ${m.number}` })),
      ),
    )
  ).flat();
  const canEdit = me.data?.permissions.includes("properties:update") ?? false;
  const links: EntityLink[] = [
    { type: "property", id: propertyId, label: property.data?.number ?? null },
    { type: "building", id: unit.data.building_id, parentId: propertyId, label: building.data?.name ?? null },
    ...(occupants.data?.tenant ? [{ type: "contract" as const, id: occupants.data.tenant.contract_id, label: occupants.data.tenant.contract_number }] : []),
    ...(occupants.data?.owner ? [{ type: "contract" as const, id: occupants.data.owner.contract_id, label: occupants.data.owner.contract_number }] : []),
    ...(occupants.data?.tenant?.members ?? []).map((m) => ({ type: "contact" as const, id: m.contact_id, label: m.display_name })),
    { type: "ticket", href: `/tickets?unit_id=${unitId}`, count: (tickets.data ?? []).length },
    { type: "ledger", id: ledgers[0]?.id ?? null },
  ];
  const unitTitle = [unit.data.number, unit.data.label].filter(Boolean).join(" ");
  const rows = (prospects.data ?? []) as { id: string; contact_id: string; status: string; delete_after: string; notes: string | null }[];
  const names: Record<string, string> = {};
  await Promise.all(
    [...new Set(rows.map((r) => r.contact_id))].map(async (id) => {
      const c = await api.GET("/api/v1/contacts/{contact_id}", { params: { path: { contact_id: id } } });
      if (c.data) names[id] = String((c.data as { display_name?: string }).display_name ?? id);
    }),
  );
  const fields = expose.data.fields as Record<string, unknown>;
  const missing = expose.data.missing as string[];
  // A63: energy certificate (from the property) and asking rent (from the rental listing)
  const blocks = {
    energy_certificate: (expose.data.energy_certificate ?? {}) as Record<string, unknown>,
    asking_rent: (expose.data.asking_rent ?? {}) as Record<string, unknown>,
  } as const;
  const listingId = (expose.data.listing_id as string | null | undefined) ?? null;
  // UI formats (CLAUDE.md section 9): dates TT.MM.JJJJ, amounts 1.234,56 EUR, translated codes.
  const DATE_KEYS = new Set(["issued_on", "valid_until"]);
  const EUR_KEYS = new Set(["net_rent", "additional_costs", "heating_costs", "deposit"]);
  const show = (k: string, v: unknown) => {
    if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) return t("none");
    if (Array.isArray(v)) return v.map(String).join(", ");
    if (DATE_KEYS.has(k)) return formatDate(String(v));
    if (EUR_KEYS.has(k)) return formatEur(String(v));
    if (k === "living_area_sqm") return `${formatDecimal(String(v), 2)} m²`;
    if (k === "value") return formatDecimal(String(v), 1);
    if (k === "unit_type" && tp.has(`unitTypes.${String(v)}`)) return tp(`unitTypes.${String(v)}`);
    if (k === "type" && tp.has(`energyCertificate.types.${String(v)}`)) return tp(`energyCertificate.types.${String(v)}`);
    return String(v);
  };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        breadcrumb={[
          { href: "/objekte", label: tu("toProperty") },
          ...(property.data ? [{ href: `/objekte/${unit.data.property_id}`, label: `${property.data.number} ${property.data.name}` }] : []),
          { label: unitTitle },
        ]}
        title={String(fields.title ?? "") || unitTitle}
      />
      <EntityLinksBar links={links} />
      <UnitMasterData unit={unit.data as unknown as UnitMaster} canEdit={canEdit} subCommunities={subCommunities} />
      <UnitDetails unit={unit.data} occupants={occupants.data ?? null} showParameters={false} />
      <VacancyValuesPanel rows={vacancyValues} />
      <MeterChangesPanel rows={meterChanges} />
      {building.data ? <EnergyCertificateForm building={building.data as unknown as EnergyBuilding} canEdit={canEdit} /> : null}
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("expose")}</h2>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {Object.entries(fields).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{t(`fields.${k}`)}</dt>
              <dd>{show(k, v)}</dd>
            </div>
          ))}
        </dl>
        {(Object.keys(blocks) as (keyof typeof blocks)[]).map((block) => (
          <div key={block} className="mt-3" data-testid={`expose-${block}`}>
            <h3 className={ui.subtitle}>{t(`fields.${block}.title`)}</h3>
            <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              {Object.entries(blocks[block]).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{t(`fields.${block}.${k}`)}</dt>
                  <dd className={EUR_KEYS.has(k) ? "tabular-nums" : undefined}>{show(k, v)}</dd>
                </div>
              ))}
            </dl>
            {block === "asking_rent" ? (
              listingId ? (
                <Link href={`/makler/${listingId}`} className="text-sm hover:underline">
                  {t("toListing")}
                </Link>
              ) : (
                <p className="text-sm text-muted">{t("noListing")}</p>
              )
            ) : null}
          </div>
        ))}
        <p className="mt-2 text-sm text-muted">
          {t("missing")}: {missing.map((m) => (m.includes(".") ? `${t(`fields.${m.split(".")[0]}.title`)} ${t(`fields.${m}`)}` : t(`fields.${m}`))).join(", ")}
        </p>
        <p className="mt-1 text-xs text-muted">{String(expose.data.note)}</p>
      </section>
      <h2 className={ui.h2}>{t("title")}</h2>
      <Prospects unitId={unitId} rows={rows} names={names} />
      <TicketsSection tickets={(tickets.data ?? []) as TicketSummary[]} />
      <AuditLogPanel entityType="unit" entityId={unitId} />
    </div>
  );
}
