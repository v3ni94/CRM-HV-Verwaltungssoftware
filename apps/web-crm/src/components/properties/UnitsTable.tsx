import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { ui } from "@/lib/ui";
import { formatQty, sortUnits, unitNumberFormatter } from "@/lib/units";

type Unit = components["schemas"]["UnitOut"];
type Occupant = NonNullable<Unit["owner"]>;

/** Owner or tenant names, each linked to its contact (operator 28.09.2026); without members the
 *  party name links to the contract. */
function OccupantLinks({ occupant }: { occupant: Occupant }) {
  const members = occupant.members ?? [];
  if (!members.length) {
    return (
      <Link href={`/vertraege/${occupant.contract_id}`} className="hover:underline">
        {occupant.party_name}
      </Link>
    );
  }
  return (
    <>
      {members.map((m, i) => (
        <span key={m.contact_id}>
          {i > 0 ? ", " : null}
          <Link href={`/kontakte/${m.contact_id}`} className="hover:underline">
            {m.display_name}
          </Link>
        </span>
      ))}
    </>
  );
}

/** Unit list of a property: natural order, number and label link to the unit page (26.09.2026). */
export function UnitsTable({ units }: { units: Unit[] }) {
  const t = useTranslations("Units");
  const tp = useTranslations("Properties");
  const rows = sortUnits(units);
  const display = unitNumberFormatter(rows.map((u) => u.number));
  return (
    <div className={`${ui.card} overflow-x-auto p-0`}>
      <table className={ui.table} data-testid="units">
        <thead>
          <tr>
            <th>{t("number")}</th>
            <th>{t("label")}</th>
            <th>{t("type")}</th>
            <th>{t("owner")}</th>
            <th>{t("tenant")}</th>
            <th className="num">{t("area")}</th>
            <th>{tp("allocation")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => {
            const href = `/vermietung/einheit/${u.id}`;
            return (
              <tr key={u.id}>
                <td className="tabular-nums font-medium">
                  <Link href={href} className="hover:underline" title={u.number}>
                    {display(u.number)}
                  </Link>
                </td>
                <td>
                  <Link href={href} className="hover:underline">
                    {u.label || u.internal_name || display(u.number)}
                  </Link>
                </td>
                <td className="text-muted">{tp(`unitTypes.${u.unit_type}`)}</td>
                <td>
                  {u.owner ? <OccupantLinks occupant={u.owner} /> : <span className="text-muted">{t("noOwner")}</span>}
                </td>
                <td>
                  {u.tenant ? <OccupantLinks occupant={u.tenant} /> : <span className="text-muted">{t("noTenant")}</span>}
                </td>
                <td className="num">
                  {u.living_area_sqm ?? u.total_area_sqm ? `${formatQty(u.living_area_sqm ?? u.total_area_sqm)} m²` : ""}
                </td>
                <td className="text-xs text-muted">
                  {(u.allocation_values ?? []).map((v) => `${v.key_code ?? ""}: ${formatQty(v.value)}`).join(" · ")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
