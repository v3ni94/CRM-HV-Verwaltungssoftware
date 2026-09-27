import { useTranslations } from "next-intl";
import Link from "next/link";

import { StatusChip } from "@/components/ui/StatusChip";
import { ui } from "@/lib/ui";

/** Deaktivierte Objekte (Status terminated) erscheinen nur für den Superadmin und grau. */
const TERMINATED = "terminated";

export type PropertyRow = {
  id: string;
  number: string;
  name: string;
  management_type: string;
  status: string;
  city?: string | null;
  street?: string | null;
  house_number?: string | null;
  owner_missing?: boolean;
};

/** Objektliste als Karten (mobil) und Tabelle; Mietverwaltung ohne aktiven Eigentümer trägt
 *  das Kennzeichen "Eigentümer fehlt" (operator 26.09.2026). Deaktivierte Objekte
 *  (operator 27.09.2026) sind grau und tragen den StatusChip Deaktiviert. */
export function PropertyList({ rows }: { rows: PropertyRow[] }) {
  const t = useTranslations("Properties");
  return (
    <>
      <ul
        className="flex flex-col gap-2 sm:hidden"
        data-testid="properties-cards"
      >
        {rows.map((p) => (
          <li key={p.id} className={`${ui.cardLink} ${p.status === TERMINATED ? "opacity-60" : ""}`} data-testid="property-card" data-status={p.status}>
            <Link href={`/objekte/${p.id}`} className="flex flex-col gap-1.5">
              <span className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {p.number} · {p.name}
                </span>
                <StatusChip domain="property" status={p.status} />
              </span>
              <span className="text-sm text-muted">
                {[p.street, p.house_number].filter(Boolean).join(" ")}
                {p.city ? `, ${p.city}` : ""}
              </span>
              <span className="flex flex-wrap gap-1">
                <span className={ui.badge}>
                  {t(`managementType.${p.management_type}`)}
                </span>
                {p.owner_missing ? (
                  <span className={ui.badgeWarning}>{t("ownerMissing")}</span>
                ) : null}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <div className={`${ui.card} hidden overflow-x-auto p-0 sm:block`}>
        <table
          className={`${ui.table} mhvp-table--sticky-col`}
          data-testid="properties"
        >
          <thead>
            <tr>
              <th>{t("number")}</th>
              <th>{t("name")}</th>
              <th>{t("address")}</th>
              <th>{t("type")}</th>
              <th>{t("ownerColumn")}</th>
              <th>{t("statusColumn")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className={p.status === TERMINATED ? "text-muted opacity-60" : undefined} data-status={p.status}>
                <td className="tabular-nums">
                  <Link
                    href={`/objekte/${p.id}`}
                    className="font-medium hover:underline"
                  >
                    {p.number}
                  </Link>
                </td>
                <td>
                  <Link href={`/objekte/${p.id}`} className="hover:underline">
                    {p.name}
                  </Link>
                </td>
                <td className="text-muted">
                  {[p.street, p.house_number].filter(Boolean).join(" ")}
                  {p.city ? `, ${p.city}` : ""}
                </td>
                <td>
                  <span className={ui.badge}>
                    {t(`managementType.${p.management_type}`)}
                  </span>
                </td>
                <td>
                  {p.owner_missing ? (
                    <span className={ui.badgeWarning}>{t("ownerMissing")}</span>
                  ) : null}
                </td>
                <td>
                  <StatusChip domain="property" status={p.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
