"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ProviderRating = {
  provider_contact_id: string;
  provider_name: string | null;
  rated_count: number;
  average: string | null;
  distribution: Record<string, number>;
};
type ProviderRatings = { mode: "off" | "staff"; enabled: boolean; note: string; providers: ProviderRating[] };

/** Bewertungen der Dienstleister (AA14-02), nur für die Verwaltung und nur hinter dem
 *  Mandantenschalter: Anzahl, Durchschnitt und Verteilung der Sterne je Dienstleister, ohne
 *  Freitexte. Dienstleister und Dritte sehen die Bewertungen nicht. */
export function ProviderRatingsPanel() {
  const t = useTranslations("ProviderRatings");
  const [data, setData] = useState<ProviderRatings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void bff<ProviderRatings>("/api/bff/portal-admin/provider-ratings").then((res) => {
      if (!live) return;
      if (res.ok) setData(res.data);
      else setError(res.message);
    });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className={`${ui.card} flex flex-col gap-2`} data-testid="provider-ratings">
      <h3 className="text-base font-semibold">{t("title")}</h3>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {data ? <p className={ui.notice}>{data.note}</p> : null}
      {data && !data.enabled ? <p className="text-sm text-muted">{t("disabled")}</p> : null}
      {data?.enabled && data.providers.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {data?.enabled && data.providers.length > 0 ? (
        <div className={ui.tableScroll}>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th scope="col" className="py-1 pr-3">
                  {t("provider")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("count")}
                </th>
                <th scope="col" className="py-1 pr-3">
                  {t("average")}
                </th>
                <th scope="col" className="py-1">
                  {t("distribution")}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.providers.map((p) => (
                <tr key={p.provider_contact_id}>
                  <th scope="row" className="py-1 pr-3 font-medium">
                    {p.provider_name ?? t("unknown")}
                  </th>
                  <td className="py-1 pr-3">{p.rated_count}</td>
                  <td className="py-1 pr-3">{p.average ? p.average.replace(".", ",") : "-"}</td>
                  <td className="py-1 text-muted">{["5", "4", "3", "2", "1"].map((star) => `${star}: ${p.distribution[star] ?? 0}`).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
