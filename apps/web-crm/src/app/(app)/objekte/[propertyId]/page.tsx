import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PageHeader } from "@/components/ui/PageHeader";
import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const STATUS_VARIANT: Record<string, StatusPillVariant> = {
  active: "success",
  onboarding: "warning",
  terminated: "neutral",
};

export default async function PropertyPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const t = await getTranslations("Properties");
  const api = serverApi();
  const path = { params: { path: { property_id: propertyId } } };
  const [{ data, error, response }, units, contacts, maintenance] = await Promise.all([
    api.GET("/api/v1/properties/{property_id}", path),
    api.GET("/api/v1/properties/{property_id}/units", path),
    api.GET("/api/v1/properties/{property_id}/contacts", path),
    api.GET("/api/v1/properties/{property_id}/maintenance", path),
  ]);
  redirectIfUnauthenticated(response);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const address = [[data.street, data.house_number].filter(Boolean).join(" "), [data.postal_code, data.city].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
  const unitRows = units.data ?? [];
  const isHoa = data.management_type !== "rental";
  const openMaintenance = (maintenance.data ?? []).filter((m) => m.status === "open");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ href: "/objekte", label: t("title") }, { label: data.number }]}
        title={data.name}
        action={
          <div className="flex flex-wrap gap-2">
            {isHoa ? (
              <Link href={`/weg/${propertyId}`} className={ui.primary}>
                {t("toHoa")}
              </Link>
            ) : null}
            <Link href="/vermietung" className={ui.button}>
              {t("toLetting")}
            </Link>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("status")}</p>
          <p className="mt-1">
            <StatusPill variant={STATUS_VARIANT[data.status] ?? "neutral"} label={t(`status.${data.status}`)} />
          </p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("type")}</p>
          <p className="mt-1 text-sm">{t(`managementType.${data.management_type}`)}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("address")}</p>
          <p className="mt-1 text-sm">{address || t("noAddress")}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("units")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{unitRows.length}</p>
        </div>
      </div>

      {(data.legal_entities ?? []).length ? (
        <section className={ui.card}>
          <h2 className={ui.subtitle}>{t("legalEntities")}</h2>
          <ul className="mt-2 flex flex-wrap gap-2 text-sm">
            {(data.legal_entities ?? []).map((e) => (
              <li key={e.id} className={ui.badgeGold}>
                {t(`entityKind.${e.kind}`)}: {e.name}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("units")}</h2>
        {unitRows.length === 0 ? (
          <p className="text-sm text-muted">{t("noUnits")}</p>
        ) : (
          <div className={`${ui.card} overflow-x-auto p-0`}>
            <div className="overflow-x-auto">
<table className={ui.table} data-testid="units">
              <thead>
                <tr>
                  <th>{t("unitNumber")}</th>
                  <th>{t("unitLabel")}</th>
                  <th>{t("unitType")}</th>
                  <th className="num">{t("livingArea")}</th>
                  <th>{t("allocation")}</th>
                </tr>
              </thead>
              <tbody>
                {unitRows.map((u) => (
                  <tr key={u.id}>
                    <td className="tabular-nums font-medium">{u.number}</td>
                    <td>{u.label ?? ""}</td>
                    <td className="text-muted">{t(`unitTypes.${u.unit_type}`)}</td>
                    <td className="num">{u.living_area_sqm ? `${String(u.living_area_sqm).replace(".", ",")} m²` : ""}</td>
                    <td className="text-xs text-muted">
                      {(u.allocation_values ?? []).map((v) => `${v.key_code ?? ""}: ${String(v.value).replace(".", ",")}`).join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
</div>
          </div>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <section className={ui.card}>
          <h2 className={ui.subtitle}>{t("contacts")}</h2>
          {(contacts.data ?? []).length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("noContacts")}</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {(contacts.data ?? []).map((c) => (
                <li key={c.id}>
                  <Link href={`/kontakte/${c.contact_id}`} className="hover:underline">
                    {c.category_code}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className={ui.card}>
          <h2 className={ui.subtitle}>{t("maintenanceOpen")}</h2>
          {openMaintenance.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("noMaintenance")}</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {openMaintenance.map((m) => (
                <li key={m.id} className="flex justify-between gap-2">
                  <span>{m.title}</span>
                  <span className="tabular-nums text-muted">{m.due_date ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
