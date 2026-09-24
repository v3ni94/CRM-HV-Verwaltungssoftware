import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PropertyCreate } from "@/components/properties/PropertyCreate";
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

/** Filter by management scope (operator 24.09.2026): rental, HOA, or HOA with SEV that has
 *  tenancy contracts. The API applies the filter; "sev" needs sev_only. */
const SCOPES = ["all", "rental", "hoa", "sev"] as const;
type Scope = (typeof SCOPES)[number];
const SCOPE_QUERY: Record<Scope, Record<string, unknown>> = {
  all: {},
  rental: { management_type: "rental" },
  hoa: {},
  sev: { sev_only: true },
};

export default async function PropertiesPage({ searchParams }: { searchParams: Promise<{ q?: string; art?: string }> }) {
  const { q, art } = await searchParams;
  const scope: Scope = (SCOPES as readonly string[]).includes(art ?? "") ? (art as Scope) : "all";
  const t = await getTranslations("Properties");
  const api = serverApi();
  const [{ data, error, response }, me] = await Promise.all([
    api.GET("/api/v1/properties", { params: { query: { page_size: 200, ...SCOPE_QUERY[scope], ...(q ? { q } : {}) } } }),
    api.GET("/api/v1/auth/me"),
  ]);
  redirectIfUnauthenticated(response);
  // "WEG" covers both HOA and HOA with SEV; the API filter takes one type, so filter here.
  const rows = (data?.items ?? []).filter((p) => scope !== "hoa" || p.management_type !== "rental");
  const canCreate = me.data?.permissions.includes("properties:create") ?? false;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageHeader eyebrow={t("area")} title={t(`scopeTitle.${scope}`)} />
        <form className="flex gap-2" role="search">
          {scope !== "all" ? <input type="hidden" name="art" value={scope} /> : null}
          <input className={ui.input} name="q" defaultValue={q ?? ""} placeholder={t("searchPlaceholder")} aria-label={t("search")} />
          <button type="submit" className={ui.button}>
            {t("search")}
          </button>
        </form>
      </div>
      <nav aria-label={t("scopeNav")} className="flex flex-wrap gap-1 border-b border-border">
        {SCOPES.map((sc) => (
          <Link
            key={sc}
            href={sc === "all" ? "/objekte" : `/objekte?art=${sc}`}
            aria-current={sc === scope ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${sc === scope ? "border-gold font-medium text-fg" : "border-transparent text-muted hover:text-fg"}`}
          >
            {t(`scope.${sc}`)}
          </Link>
        ))}
      </nav>
      {scope === "sev" ? <p className={ui.notice}>{t("sevHint")}</p> : null}
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t(`emptyScope.${scope}`)}</p>
      ) : (
        <>
          <ul className="flex flex-col gap-2 sm:hidden" data-testid="properties-cards">
            {rows.map((p) => (
              <li key={p.id} className={ui.cardLink} data-testid="property-card">
                <Link href={`/objekte/${p.id}`} className="flex flex-col gap-1.5">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">
                      {p.number} · {p.name}
                    </span>
                    <StatusPill variant={STATUS_VARIANT[p.status] ?? "neutral"} label={t(`status.${p.status}`)} />
                  </span>
                  <span className="text-sm text-muted">
                    {[p.street, p.house_number].filter(Boolean).join(" ")}
                    {p.city ? `, ${p.city}` : ""}
                  </span>
                  <span className={ui.badge}>{t(`managementType.${p.management_type}`)}</span>
                </Link>
              </li>
            ))}
          </ul>
          <div className={`${ui.card} hidden overflow-x-auto p-0 sm:block`}>
            <table className={`${ui.table} mhvp-table--sticky-col`} data-testid="properties">
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
                    <td className="text-muted">
                      {[p.street, p.house_number].filter(Boolean).join(" ")}
                      {p.city ? `, ${p.city}` : ""}
                    </td>
                    <td>
                      <span className={ui.badge}>{t(`managementType.${p.management_type}`)}</span>
                    </td>
                    <td>
                      <StatusPill variant={STATUS_VARIANT[p.status] ?? "neutral"} label={t(`status.${p.status}`)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {canCreate ? <PropertyCreate /> : null}
    </div>
  );
}
