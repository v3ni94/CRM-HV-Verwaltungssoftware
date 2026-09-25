import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate, formatEur } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { art?: string; status?: string; q?: string };

type Listing = {
  id: string;
  property_number: string | null;
  unit_number: string | null;
  title: string;
  price: string | null;
  available_from: string | null;
  status: string;
};

const STATUSES = ["draft", "active", "reserved", "inactive"] as const;

/** U-Protokoll (apps/u-protokoll): separate PHP app for handover protocols, linked here with
 *  the same pattern as MHVP_DMS_URL on the DMS page; it runs in the stack under its own host. */
const UPROTOKOLL_URL = (process.env.MHVP_UPROTOKOLL_URL ?? "https://uprotokoll.mueller-holding.ag").replace(/\/+$/, "");

/** Makler (M28-01, stage 2): listings for rent and sale. FLOWFACT is not connected yet;
 *  publication_status stays a placeholder field until its interface is documented. */
export default async function BrokerPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("Broker");
  const kind = params.art === "sale" ? "sale" : "rental";
  const api = serverApi();
  const query = {
    kind,
    ...(params.status ? { status: params.status } : {}),
    ...(params.q ? { q: params.q } : {}),
  };
  const { data, error, response } = await api.GET("/api/v1/letting/listings", { params: { query } });
  redirectIfUnauthenticated(response);
  const listings = (data ?? []) as unknown as Listing[];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        action={
          <Link href="/makler/neu" className={ui.primary}>
            {t("newListing")}
          </Link>
        }
      />
      <p className={ui.notice}>{t("flowfactNotice")}</p>
      <section className={`${ui.card} flex flex-wrap items-center justify-between gap-3`}>
        <div>
          <h2 className="mhvp-label">{t("uprotokollTitle")}</h2>
          <p className="mt-1 text-sm">{t("uprotokollText")}</p>
        </div>
        <a href={UPROTOKOLL_URL} target="_blank" rel="noopener noreferrer" className={ui.primary}>
          {t("uprotokollOpen")}
        </a>
      </section>
      <nav className="flex gap-2 text-sm">
        <Link href={`/makler?art=rental${params.status ? `&status=${params.status}` : ""}`} className={kind === "rental" ? ui.badgeGold : ui.badge}>
          {t("tabRental")}
        </Link>
        <Link href={`/makler?art=sale${params.status ? `&status=${params.status}` : ""}`} className={kind === "sale" ? ui.badgeGold : ui.badge}>
          {t("tabSale")}
        </Link>
      </nav>
      <form className="grid gap-3 md:grid-cols-[auto_1fr_auto] md:items-end" role="search">
        <input type="hidden" name="art" value={kind} />
        <div>
          <label htmlFor="status" className={ui.label}>
            Status
          </label>
          <select id="status" name="status" defaultValue={params.status ?? ""} className={ui.input}>
            <option value="">{t("statusAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`status.${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="q" className={ui.label}>
            {t("search")}
          </label>
          <input id="q" name="q" defaultValue={params.q ?? ""} placeholder={t("searchPlaceholder")} className={ui.input} />
        </div>
        <button type="submit" className={ui.button}>
          {t("search")}
        </button>
      </form>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : listings.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="listings">
            <thead>
              <tr>
                <th>{t("property")}</th>
                <th>{t("unit")}</th>
                <th>{t("listingTitle")}</th>
                <th className="text-right">{t("price")}</th>
                <th>{t("availableFrom")}</th>
                <th>Status</th>
                <th>{t("publication")}</th>
              </tr>
            </thead>
            <tbody>
              {listings.map((l) => (
                <tr key={l.id}>
                  <td>{l.property_number}</td>
                  <td>{l.unit_number}</td>
                  <td>
                    <Link href={`/makler/${l.id}`} className="hover:underline">
                      {l.title}
                    </Link>
                  </td>
                  <td className="text-right tabular-nums">{formatEur(l.price)}</td>
                  <td>{formatDate(l.available_from)}</td>
                  <td>
                    <span className={ui.badge}>{t(`status.${l.status}`)}</span>
                  </td>
                  <td className="text-muted">{t("notPublished")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
