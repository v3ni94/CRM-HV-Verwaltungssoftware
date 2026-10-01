"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type OccupancyRow = {
  unit_id: string;
  unit_number: string;
  unit_label: string | null;
  unit_type: string;
  tenancy_contract_id: string | null;
  tenant_party: string | null;
  ownership_contract_id: string | null;
  owner_party: string | null;
  vacant: boolean;
};

/** Occupancy list of a property for a reference date (M5-04, milestone M5): every unit with the
 *  tenant and the owner valid on that day and a vacancy mark. The date is optional, empty means
 *  today (evaluated by the API). Reading needs contracts:read; the list changes nothing. */
export function OccupancyList({ propertyId }: { propertyId: string }) {
  const t = useTranslations("OccupancyList");
  const tp = useTranslations("Properties");
  const [asOf, setAsOf] = useState("");
  const [rows, setRows] = useState<OccupancyRow[] | null>(null);
  const [shownFor, setShownFor] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [onlyVacant, setOnlyVacant] = useState(false);

  const load = useCallback(
    async (date: string) => {
      setError(null);
      const query = date ? `?as_of=${encodeURIComponent(date)}` : "";
      const res = await bff<OccupancyRow[]>(`/api/bff/properties/${propertyId}/occupancy${query}`);
      if (res.ok) {
        setRows(res.data ?? []);
        setShownFor(date);
      } else {
        setError(res.message);
      }
    },
    [propertyId],
  );

  useEffect(() => {
    void load("");
  }, [load]);

  const visible = (rows ?? []).filter((r) => !onlyVacant || r.vacant);
  const vacantCount = (rows ?? []).filter((r) => r.vacant).length;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="occupancy-title" data-testid="occupancy-list">
      <h2 id="occupancy-title" className={ui.h2}>
        {t("title")}
      </h2>
      <form
        aria-label={t("title")}
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void load(asOf);
        }}
      >
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("asOf")}</span>
          <input type="date" className={ui.input} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
        <button type="submit" className={ui.secondary}>
          {t("show")}
        </button>
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyVacant} onChange={(e) => setOnlyVacant(e.target.checked)} />
          {t("onlyVacant")}
        </label>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? (
        !error ? <p className="text-sm text-muted">{t("loading")}</p> : null
      ) : (
        <>
          <p className={ui.help} data-testid="occupancy-summary">
            {t("summary", {
              date: shownFor ? formatDate(shownFor) : t("today"),
              units: rows.length,
              vacant: vacantCount,
            })}
          </p>
          {visible.length === 0 ? (
            <p className="text-sm text-muted">{t("empty")}</p>
          ) : (
            <div className={ui.tableScroll}>
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("unit")}</th>
                    <th>{t("type")}</th>
                    <th>{t("tenant")}</th>
                    <th>{t("owner")}</th>
                    <th>{t("status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.unit_id} data-testid="occupancy-row">
                      <td>
                        <Link href={`/vermietung/einheit/${r.unit_id}`} className="hover:underline">
                          {[r.unit_number, r.unit_label].filter(Boolean).join(" ")}
                        </Link>
                      </td>
                      <td>{tp.has(`unitTypes.${r.unit_type}`) ? tp(`unitTypes.${r.unit_type}`) : r.unit_type}</td>
                      <td>
                        {r.tenant_party ? (
                          r.tenancy_contract_id ? (
                            <Link href={`/vertraege/${r.tenancy_contract_id}`} className="hover:underline">
                              {r.tenant_party}
                            </Link>
                          ) : (
                            r.tenant_party
                          )
                        ) : (
                          <span className="text-muted">{t("none")}</span>
                        )}
                      </td>
                      <td>
                        {r.owner_party ? (
                          r.ownership_contract_id ? (
                            <Link href={`/vertraege/${r.ownership_contract_id}`} className="hover:underline">
                              {r.owner_party}
                            </Link>
                          ) : (
                            r.owner_party
                          )
                        ) : (
                          <span className="text-muted">{t("none")}</span>
                        )}
                      </td>
                      <td>
                        <span className={r.vacant ? ui.badgeWarning : ui.badge}>{r.vacant ? t("vacant") : t("occupied")}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
