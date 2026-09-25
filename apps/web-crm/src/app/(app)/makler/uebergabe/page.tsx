import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PageHeader } from "@/components/ui/PageHeader";
import type { Protocol } from "@/components/handover/types";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { formatDate } from "@/lib/format";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Params = { q?: string; status?: string; art?: string; archiv?: string };

const STATUSES = ["draft", "in_progress", "signature_pending", "completed", "sent", "archived", "cancelled"] as const;

/** Übergabeprotokolle (M30) under Makler: list with search, status and archive filter. The
 *  row colour follows the state: red without content, gold open, green completed, grey
 *  cancelled or archived. */
export default async function HandoverListPage({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const t = await getTranslations("Handover");
  const api = serverApi();
  const query = {
    ...(params.q ? { q: params.q } : {}),
    ...(params.status ? { status: params.status } : {}),
    ...(params.art ? { kind: params.art } : {}),
    ...(params.archiv === "1" ? { include_archived: true } : {}),
    page_size: 100,
  };
  const { data, error, response } = await api.GET("/api/v1/handover/protocols", { params: { query } });
  redirectIfUnauthenticated(response);
  const rows = ((data as { items?: Protocol[] } | undefined)?.items ?? []) as Protocol[];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title={t("title")}
        breadcrumb={[{ href: "/makler", label: t("broker") }]}
        action={
          <Link href="/makler/uebergabe/neu" className={ui.primary}>
            {t("new")}
          </Link>
        }
      />
      <form className="grid gap-3 md:grid-cols-[1fr_auto_auto_auto_auto] md:items-end" role="search">
        <div>
          <label htmlFor="q" className={ui.label}>
            {t("search")}
          </label>
          <input id="q" name="q" defaultValue={params.q ?? ""} placeholder={t("searchPlaceholder")} className={ui.input} />
        </div>
        <div>
          <label htmlFor="status" className={ui.label}>
            Status
          </label>
          <select id="status" name="status" defaultValue={params.status ?? ""} className={ui.input}>
            <option value="">{t("statusAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statusLabel.${s}`)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="art" className={ui.label}>
            {t("create.kind")}
          </label>
          <select id="art" name="art" defaultValue={params.art ?? ""} className={ui.input}>
            <option value="">{t("statusAll")}</option>
            <option value="rental">{t("create.kinds.rental")}</option>
            <option value="sale">{t("create.kinds.sale")}</option>
            <option value="general">{t("create.kinds.general")}</option>
          </select>
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input type="checkbox" name="archiv" value="1" defaultChecked={params.archiv === "1"} />
          {t("showArchived")}
        </label>
        <button type="submit" className={ui.button}>
          {t("search")}
        </button>
      </form>
      {!data ? (
        <p role="alert" className={ui.alert}>
          {problemMessage(error as Problem | undefined, response.status)}
        </p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <table className={ui.table} data-testid="handover-list">
            <thead>
              <tr>
                <th>{t("list.number")}</th>
                <th>Status</th>
                <th>{t("list.object")}</th>
                <th>{t("list.participants")}</th>
                <th>{t("list.date")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/makler/uebergabe/${r.id}`} className="font-medium hover:underline">
                      {r.number}
                      {r.version > 1 ? ` V${r.version}` : ""}
                    </Link>
                    <div className="text-xs text-muted">
                      {t(`create.kinds.${r.kind}`)}
                      {r.ticket_number ? ` · ${r.ticket_number}` : ""}
                    </div>
                  </td>
                  <td>
                    <span className={r.finalized ? ui.badgeSuccess : r.status === "cancelled" || r.status === "archived" ? ui.badge : r.address ? ui.badgeGold : ui.badgeDanger}>
                      {t(`statusLabel.${r.status}`)}
                    </span>
                  </td>
                  <td>
                    {r.address || <span className="text-muted">–</span>}
                    {r.unit_number ? <div className="text-xs text-muted">{[r.unit_number, r.unit_label].filter(Boolean).join(" ")}</div> : null}
                  </td>
                  <td>{r.participants_summary || <span className="text-muted">–</span>}</td>
                  <td className="whitespace-nowrap">{formatDate(r.handover_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
