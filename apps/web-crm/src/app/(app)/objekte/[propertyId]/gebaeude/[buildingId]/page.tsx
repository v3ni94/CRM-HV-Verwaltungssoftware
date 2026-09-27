import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AuditLogPanel } from "@/components/common/AuditLogPanel";
import { EntityLinksBar } from "@/components/common/EntityLinksBar";
import { BuildingMasterData, type BuildingMaster } from "@/components/properties/BuildingMasterData";
import { EnergyCertificateForm, type EnergyBuilding } from "@/components/properties/EnergyCertificateForm";
import { UnitsTable } from "@/components/properties/UnitsTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Gebäudeseite (4.3, AP5): Stammdaten an Ort und Stelle editierbar, Energieausweis des
 *  Gebäudes, Einheiten des Gebäudes, Ereignisprotokoll. */
export default async function BuildingPage({ params }: { params: Promise<{ propertyId: string; buildingId: string }> }) {
  const { propertyId, buildingId } = await params;
  const [t, tp] = await Promise.all([getTranslations("Buildings"), getTranslations("Properties")]);
  const api = serverApi();
  const [building, property, units, me] = await Promise.all([
    api.GET("/api/v1/buildings/{building_id}", { params: { path: { building_id: buildingId } } }),
    api.GET("/api/v1/properties/{property_id}", { params: { path: { property_id: propertyId } } }),
    api.GET("/api/v1/properties/{property_id}/units", { params: { path: { property_id: propertyId }, query: { with_occupants: true } } }),
    getMe(),
  ]);
  redirectIfUnauthenticated(building.response);
  if (!building.data || building.data.property_id !== propertyId) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(building.error as Problem | undefined, building.data ? 404 : building.response.status)}
      </p>
    );
  }
  const canEdit = me.data?.permissions.includes("properties:update") ?? false;
  const unitRows = (units.data ?? []).filter((u) => u.building_id === buildingId);
  const address = [building.data.street, building.data.house_number, building.data.address_addition].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[
          { href: "/objekte", label: tp("title") },
          ...(property.data ? [{ href: `/objekte/${propertyId}`, label: `${property.data.number} ${property.data.name}` }] : []),
          { label: building.data.name },
        ]}
        eyebrow={t("title")}
        title={building.data.name}
        description={address || undefined}
        action={
          <Link href={`/objekte/${propertyId}`} className={ui.button}>
            {t("toProperty")}
          </Link>
        }
      />
      <EntityLinksBar
        links={[
          { type: "property", id: propertyId, label: property.data ? property.data.number : null },
          { type: "unit", href: "#einheiten", count: unitRows.length, label: t("unitsOfBuilding") },
          { type: "ticket", href: `/tickets?property_id=${propertyId}` },
        ]}
      />
      <BuildingMasterData building={building.data as unknown as BuildingMaster} canEdit={canEdit} />
      <EnergyCertificateForm building={building.data as unknown as EnergyBuilding} canEdit={canEdit} />
      <section id="einheiten" className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("unitsOfBuilding")}</h2>
        {unitRows.length === 0 ? <p className="text-sm text-muted">{t("noUnits")}</p> : <UnitsTable units={unitRows} />}
      </section>
      <AuditLogPanel entityType="building" entityId={buildingId} />
    </div>
  );
}
