import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { formatQty } from "@/lib/units";

type Unit = components["schemas"]["UnitOut"];
type Occupants = components["schemas"]["UnitOccupantsOut"];
type Occupant = components["schemas"]["OccupantOut"];

const LEGACY_LABELS: Record<string, string> = {
  quelle: "Quelle",
  stand: "Stand",
  eigentuemer: "Eigentümer",
  hausgeld_vereinbart: "Hausgeld vereinbart",
  mieter: "Mieter",
  miete_vereinbart: "Miete vereinbart",
};

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "ja" : "nein";
  if (typeof value === "object") return JSON.stringify(value);
  const text = String(value);
  return /^\d{4}-\d{2}-\d{2}(T.*)?$/.test(text) ? formatDate(text) : text;
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="contents">
      <dt className="text-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Party({ occupant, withRent }: { occupant: Occupant; withRent?: boolean }) {
  const t = useTranslations("Units");
  const members = occupant.members ?? [];
  return (
    <div className="flex flex-col gap-1 text-sm">
      {members.length ? (
        <ul className="flex flex-col gap-0.5">
          {members.map((m) => (
            <li key={m.contact_id}>
              <Link href={`/kontakte/${m.contact_id}`} className="font-medium hover:underline">
                {m.display_name}
              </Link>
              {m.share_percent ? <span className="text-muted">, {t("share")} {formatQty(m.share_percent)} %</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="font-medium">{occupant.party_name}</p>
      )}
      <p className="text-muted">
        {t("since")} {formatDate(occupant.start_date)}
        {occupant.end_date ? `, ${t("until")} ${formatDate(occupant.end_date)}` : ""}, {t("contract")} {occupant.contract_number}
      </p>
      {withRent && occupant.rent_gross ? (
        <p>
          {t("rent")}: <span className="tabular-nums">{formatEur(occupant.rent_gross)}</span>
        </p>
      ) : null}
    </div>
  );
}

/** Unit page body: all parameters, current owner and tenant, ended contracts (26.09.2026). */
export function UnitDetails({ unit, occupants }: { unit: Unit; occupants: Occupants | null }) {
  const t = useTranslations("Units");
  const tp = useTranslations("Properties");
  const custom = { ...(unit.custom_fields ?? {}) } as Record<string, unknown>;
  const legacy = custom.altsystem as Record<string, unknown> | undefined;
  delete custom.altsystem;
  const values = unit.allocation_values ?? [];
  const mea = values.filter((v) => v.key_code === "MEA");
  const address = [[unit.street, unit.house_number].filter(Boolean).join(" "), [unit.postal_code, unit.city].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
  const area = (v: string | null | undefined) => (v ? `${formatQty(v)} m²` : "");
  const history = occupants?.history ?? [];
  return (
    <div className="flex flex-col gap-4" data-testid="unit-details">
      <div className="grid gap-4 md:grid-cols-2">
        <section className={ui.card} data-testid="unit-owner">
          <h2 className={ui.subtitle}>{t("owner")}</h2>
          <div className="mt-2">
            {occupants?.owner ? <Party occupant={occupants.owner} /> : <p className="text-sm text-muted">{t("noOwner")}</p>}
          </div>
        </section>
        <section className={ui.card} data-testid="unit-tenant">
          <h2 className={ui.subtitle}>{t("tenant")}</h2>
          <div className="mt-2">
            {occupants?.tenant ? <Party occupant={occupants.tenant} withRent /> : <p className="text-sm text-muted">{t("noTenant")}</p>}
          </div>
        </section>
      </div>

      <section className={ui.card} data-testid="unit-parameters">
        <h2 className={ui.h2}>{t("parameters")}</h2>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <Field label={t("number")} value={unit.number} />
          <Field label={t("label")} value={unit.label ?? ""} />
          <Field label={t("internalName")} value={unit.internal_name ?? ""} />
          <Field label={t("type")} value={tp(`unitTypes.${unit.unit_type}`)} />
          <Field label={t("location")} value={unit.location ?? ""} />
          <Field label={t("floor")} value={unit.floor ?? ""} />
          <Field label={t("livingArea")} value={area(unit.living_area_sqm)} />
          <Field label={t("totalArea")} value={area(unit.total_area_sqm)} />
          <Field label={t("mea")} value={mea.map((v) => formatQty(v.value)).join(", ")} />
          <Field label={t("rooms")} value={formatQty(unit.rooms)} />
          <Field label={t("bedrooms")} value={show(unit.bedrooms)} />
          <Field label={t("bathrooms")} value={show(unit.bathrooms)} />
          <Field label={t("cellar")} value={unit.cellar_number ?? ""} />
          <Field label={t("modernization")} value={show(unit.last_modernization_year)} />
          <Field label={t("features")} value={unit.features ?? ""} />
          <Field label={t("address")} value={address} />
          <Field label={t("vatOption")} value={unit.vat_option ?? ""} />
        </dl>
      </section>

      <section className={ui.card} data-testid="unit-allocation">
        <h2 className={ui.h2}>{t("allocationKeys")}</h2>
        {values.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("noAllocation")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("key")}</th>
                  <th className="num">{t("value")}</th>
                  <th>{t("validFrom")}</th>
                  <th>{t("validTo")}</th>
                </tr>
              </thead>
              <tbody>
                {values.map((v) => (
                  <tr key={v.id}>
                    <td>
                      {v.key_name ?? v.key_code}
                      {v.key_name && v.key_code ? <span className="text-muted"> ({v.key_code})</span> : null}
                    </td>
                    <td className="num">{formatQty(v.value)}</td>
                    <td>{formatDate(v.valid_from)}</td>
                    <td>{formatDate(v.valid_to)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {Object.keys(custom).length || legacy ? (
        <section className={ui.card} data-testid="unit-custom">
          {Object.keys(custom).length ? (
            <>
              <h2 className={ui.subtitle}>{t("customFields")}</h2>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {Object.entries(custom).map(([k, v]) => (
                  <Field key={k} label={k} value={show(v)} />
                ))}
              </dl>
            </>
          ) : null}
          {legacy && typeof legacy === "object" ? (
            <div className="mt-3" data-testid="unit-legacy">
              <h3 className={ui.subtitle}>{t("legacy")}</h3>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                {Object.entries(legacy).map(([k, v]) => (
                  <Field key={k} label={LEGACY_LABELS[k] ?? k} value={show(v)} />
                ))}
              </dl>
            </div>
          ) : null}
        </section>
      ) : null}

      <details className={ui.card} data-testid="unit-history">
        <summary className="cursor-pointer font-medium">
          {t("history")} ({history.length})
        </summary>
        {history.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("noHistory")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-3">
            {history.map((o) => (
              <li key={o.contract_id}>
                <p className={ui.subtitle}>{t(`kind.${o.kind === "ownership" ? "ownership" : "tenancy"}`)}</p>
                <Party occupant={o} withRent={o.kind === "tenancy"} />
              </li>
            ))}
          </ul>
        )}
      </details>
    </div>
  );
}
