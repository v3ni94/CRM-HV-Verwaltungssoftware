import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PropertyCreate } from "@/components/properties/PropertyCreate";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const STATUS_CLASS: Record<string, string> = {
  active: ui.badgeSuccess,
  onboarding: ui.badgeWarning,
  terminated: ui.badge,
};

export default async function PropertiesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams;
  const t = await getTranslations("Properties");
  const api = serverApi();
  const [{ data, error, response }, me] = await Promise.all([
    api.GET("/api/v1/properties", { params: { query: { page_size: 200, ...(q ? { q } : {}) } } }),
    api.GET("/api/v1/auth/me"),
  ]);
  redirectIfUnauthenticated(response);
  const rows = data?.items ?? [];
  const canCreate = me.data?.permissions.includes("properties:create") ?? false;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className={ui.subtitle}>{t("area")}</p>
          <h1 className={ui.title}>{t("title")}</h1>
        </div>
        <form className="flex gap-2" role="search">
          <input className={ui.input} name="q" defaultValue={q ?? ""} placeholder={t("searchPlaceholder")} aria-label={t("search")} />
          <button type="submit" className={ui.button}>
            {t("search")}
          </button>
        </form>
      </div>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="properties">
            <thead>
              <tr>
                <th>{t("number")}</th>
                <th>{t("name")}</th>
                <th>{t("address")}</th>
                <th>{t("type")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td className="tabular-nums">
                    <Link href={`/objekte/${p.id}`} className="font-medium hover:underline">
                      {p.number}
                    </Link>
                  </td>
                  <td>
                    <Link href={`/objekte/${p.id}`} className="hover:underline">
                      {p.name}
                    </Link>
                  </td>
                  <td className="text-muted">{[p.street, p.house_number].filter(Boolean).join(" ")}{p.city ? `, ${p.city}` : ""}</td>
                  <td>
                    <span className={ui.badge}>{t(`managementType.${p.management_type}`)}</span>
                  </td>
                  <td>
                    <span className={STATUS_CLASS[p.status] ?? ui.badge}>{t(`status.${p.status}`)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canCreate ? <PropertyCreate /> : null}
    </div>
  );
}
