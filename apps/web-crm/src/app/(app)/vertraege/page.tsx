import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { ContractOut } from "@/components/contracts/ContractForm";
import { ContractList, ContractSearch } from "@/components/contracts/ContractList";
import { PageHeader } from "@/components/ui/PageHeader";
import { SavedFilters } from "@/components/workspace/SavedFilters";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Verträge (Miete, WEG, SEV): Liste mit Link zum Formular (A88). Versionen erscheinen als
 *  eigene Zeilen, sortiert nach Nummer und Version wie in der API. */
export default async function ContractsPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const t = await getTranslations("ContractForm");
  const ta = await getTranslations("ContractApproval");
  const ts = await getTranslations("SepaOverview");
  // Filters from the URL (the object page links to /vertraege?property_id=..., the unit page
  // to unit_id=...); only well formed ids are passed on to GET /contracts.
  const params = (await searchParams) ?? {};
  const query = new URLSearchParams({ limit: "500" });
  const filters: string[] = [];
  const hidden: Record<string, string> = {};
  for (const key of ["property_id", "unit_id"] as const) {
    const raw = params[key];
    const id = Array.isArray(raw) ? raw[0] : raw;
    if (id && /^[0-9a-f-]{36}$/i.test(id)) {
      query.set(key, id);
      filters.push(key);
      hidden[key] = id;
    }
  }
  // Free text search by name, property or unit (operator feedback 28.09.2026), server side.
  const rawQ = Array.isArray(params.q) ? params.q[0] : params.q;
  const q = (rawQ ?? "").trim().slice(0, 200);
  if (q) query.set("q", q);
  const [me, response] = await Promise.all([getMe(), serverFetch(`/api/v1/contracts?${query.toString()}`)]);
  redirectIfUnauthenticated(response);
  const rows = response.ok ? ((await response.json()) as ContractOut[]) : null;
  const pending = (rows ?? []).filter((c) => c.approval_status === "pending").length;
  const canCreate = (me.data?.permissions ?? []).includes("contracts:create");

  return (
    <div className={ui.pageGap}>
      <PageHeader
        title={t("page.list")}
        description={t("page.listDescription")}
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/vertraege/sepa" className={ui.button}>
              {ts("link")}
            </Link>
            <Link href="/vertraege/freigabe" className={ui.button}>
              {ta("link")}
              {pending > 0 ? ` (${pending})` : ""}
            </Link>
            {canCreate ? (
              <Link href="/vertraege/neu" className={ui.primary}>
                {t("page.new")}
              </Link>
            ) : null}
          </div>
        }
      />
      {filters.length ? (
        <p className={ui.help} data-testid="contracts-filter">
          {t("page.filtered", { filter: filters.map((f) => t(`page.filters.${f}`)).join(", ") })}{" "}
          <Link href="/vertraege" className="underline">
            {t("page.clearFilter")}
          </Link>
        </p>
      ) : null}
      <ContractSearch q={q} hidden={hidden} />
      <SavedFilters resource="contracts" basePath="/vertraege" current={{ ...hidden, ...(q ? { q } : {}) }} />
      {rows === null ? (
        <p role="alert" className={ui.alert}>
          {t("page.listError")}
        </p>
      ) : rows.length === 0 ? (
        <p className={ui.help}>{q ? t("page.searchNoHits", { q }) : t("page.empty")}</p>
      ) : (
        <ContractList rows={rows} />
      )}
    </div>
  );
}
