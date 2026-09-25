import { getTranslations } from "next-intl/server";

import { Prospects } from "@/components/letting/Prospects";
import { TicketsSection, type TicketSummary } from "@/components/tickets/TicketsSection";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi } from "@/lib/api-server";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function LettingUnitPage({ params }: { params: Promise<{ unitId: string }> }) {
  const { unitId } = await params;
  const t = await getTranslations("Prospects");
  const api = serverApi();
  const [expose, prospects, tickets] = await Promise.all([
    api.GET("/api/v1/letting/units/{unit_id}/expose", { params: { path: { unit_id: unitId } } }),
    api.GET("/api/v1/letting/prospects", { params: { query: { unit_id: unitId } } }),
    api.GET("/api/v1/tickets", { params: { query: { unit_id: unitId, limit: 50 } } }),
  ]);
  redirectIfUnauthenticated(expose.response);
  if (!expose.data) return <p role="alert" className={ui.alert}>{problemMessage(expose.error as Problem | undefined, expose.response.status)}</p>;
  const rows = (prospects.data ?? []) as { id: string; contact_id: string; status: string; delete_after: string; notes: string | null }[];
  const names: Record<string, string> = {};
  await Promise.all(
    [...new Set(rows.map((r) => r.contact_id))].map(async (id) => {
      const c = await api.GET("/api/v1/contacts/{contact_id}", { params: { path: { contact_id: id } } });
      if (c.data) names[id] = String((c.data as { display_name?: string }).display_name ?? id);
    }),
  );
  const fields = expose.data.fields as Record<string, unknown>;
  const missing = expose.data.missing as string[];
  return (
    <div className="flex flex-col gap-4">
      <PageHeader breadcrumb={[{ href: "/vermietung", label: t("title") }]} title={String(fields.title ?? "")} />
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("expose")}</h2>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {Object.entries(fields).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{t(`fields.${k}`)}</dt>
              <dd>{v === null || v === "" ? t("none") : String(v)}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 text-sm text-muted">
          {t("missing")}: {missing.map((m) => t(`fields.${m}`)).join(", ")}
        </p>
        <p className="mt-1 text-xs text-muted">{String(expose.data.note)}</p>
      </section>
      <h2 className={ui.h2}>{t("title")}</h2>
      <Prospects unitId={unitId} rows={rows} names={names} />
      <TicketsSection tickets={(tickets.data ?? []) as TicketSummary[]} />
    </div>
  );
}
