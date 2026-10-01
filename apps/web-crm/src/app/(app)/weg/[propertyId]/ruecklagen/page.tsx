import { getTranslations } from "next-intl/server";

import { ReserveDevelopment, type ReserveBlock } from "@/components/hoa/ReserveDevelopment";
import { ReserveCreateForm, ReserveMovementForm } from "@/components/hoa/ReserveForms";
import { ReserveStatementPanel } from "@/components/hoa/ReserveStatementPanel";
import { ReserveMovementList, ReservePosition, type ReserveRow } from "@/components/hoa/ReservePositions";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { hoaContext } from "@/lib/hoa";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Statement = { id: string; year: number; version: number; status: string; snapshot?: { reserve?: ReserveBlock } | null };

/** Zweckgebundene Rücklagen der Gemeinschaft (W08, M24-01): Anlage, Mittelverwendung und die
 *  Entwicklung je Rücklage aus der jüngsten berechneten Abrechnung. */
export default async function ReservesPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const [t, th] = await Promise.all([getTranslations("HoaReserves"), getTranslations("Hoa")]);
  const ctx = await hoaContext(propertyId);
  redirectIfUnauthenticated(ctx.response);
  if (!ctx.ledger) return <p role="alert" className={ui.alert}>{t("noLedger")}</p>;
  const [reserves, statements] = await Promise.all([
    ctx.api.GET("/api/v1/hoa/reserves", { params: { query: { ledger_id: ctx.ledger.id } } }),
    ctx.api.GET("/api/v1/hoa/statements", { params: { query: { ledger_id: ctx.ledger.id } } }),
  ]);
  const list = (reserves.data ?? []) as unknown as ReserveRow[];
  const year = (((statements.data ?? []) as unknown as Statement[])[0]?.year ?? new Date().getFullYear()) as number;
  // The list carries no snapshot: the newest versions are read until one has a reserve block.
  const candidates = ((statements.data ?? []) as unknown as Statement[]).slice(0, 5);
  let latest: Statement | null = null;
  for (const c of candidates) {
    const detail = await ctx.api.GET("/api/v1/hoa/statements/{statement_id}", { params: { path: { statement_id: c.id } } });
    const full = detail.data as unknown as Statement | undefined;
    if (full?.snapshot?.reserve) {
      latest = full;
      break;
    }
  }
  return (
    <div className="flex flex-col gap-5">
      <PageHeader breadcrumb={[{ href: "/weg", label: th("title") }, { href: `/weg/${propertyId}`, label: `${ctx.property?.number ?? ""}` }]} title={t("title")} />
      <p className={ui.help}>{t("hint")}</p>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("list")}</h2>
        {list.length === 0 ? <p className="text-sm text-muted">{t("none")}</p> : null}
        <ul className="flex flex-col gap-1 text-sm" data-testid="reserve-list">
          {list.map((r) => (
            <ReservePosition key={r.id} reserve={r} year={year} />
          ))}
        </ul>
        <ReserveCreateForm ledgerId={ctx.ledger.id} />
      </section>
      {latest?.snapshot?.reserve ? (
        <>
          <p className="text-sm text-muted">{t("basedOn", { year: latest.year, version: latest.version })}</p>
          <ReserveDevelopment block={latest.snapshot.reserve} />
          {list.length ? <ReserveMovementForm statementId={latest.id} reserves={list.map((r) => ({ id: r.id, name: r.name }))} /> : null}
          <ReserveMovementList statementId={latest.id} reserves={list} editable={latest.status === "draft"} />
        </>
      ) : (
        <p className="text-sm text-muted">{t("noStatement")}</p>
      )}
      <ReserveStatementPanel ledgerId={ctx.ledger.id} hoaStatementId={latest?.id ?? null} />
    </div>
  );
}
