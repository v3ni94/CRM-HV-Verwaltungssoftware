import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { HoaCreate } from "@/components/hoa/HoaForms";
import { ResolutionTable } from "@/components/hoa/ResolutionTable";
import { redirectIfUnauthenticated } from "@/lib/api-server";
import { formatDate, formatDateTime } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function HoaDetailPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const [t, tw] = await Promise.all([getTranslations("Hoa"), getTranslations("HoaWork")]);
  const ctx = await hoaContext(propertyId);
  redirectIfUnauthenticated(ctx.response);
  if (!ctx.property) return <p role="alert" className={ui.alert}>{t("noEntity")}</p>;
  const base = `/weg/${propertyId}`;
  if (!ctx.entity) return <p className="text-sm text-muted">{t("noEntity")}</p>;
  const [resolutions, plans, statements, meetings] = await Promise.all([
    ctx.api.GET("/api/v1/hoa/resolutions", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.ledger ? ctx.api.GET("/api/v1/hoa/plans", { params: { query: { ledger_id: ctx.ledger.id } } }) : null,
    ctx.ledger ? ctx.api.GET("/api/v1/hoa/statements", { params: { query: { ledger_id: ctx.ledger.id } } }) : null,
    ctx.api.GET("/api/v1/hoa/meetings", { params: { query: { legal_entity_id: ctx.entity.id } } }),
  ]);
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">
        {ctx.property.number} {ctx.property.name}
      </h1>
      <p className={ui.notice}>{t("gateNotice")}</p>
      {!ctx.ledger ? <p className="text-sm text-muted">{tw("noLedger")}</p> : null}
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{tw("plans")}</h2>
        <ul className="text-sm">
          {(plans?.data ?? []).map((p) => (
            <li key={String(p.id)}>
              <Link href={`${base}/plan/${String(p.id)}`} className="hover:underline">
                {String(p.year)} · V{String(p.version)} · {tw(`status.${String(p.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
        <HoaCreate kind="plan" ledgerId={ctx.ledger?.id} legalEntityId={ctx.entity.id} basePath={base} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{tw("statements")}</h2>
        <ul className="text-sm">
          {(statements?.data ?? []).map((s) => (
            <li key={String(s.id)}>
              <Link href={`${base}/abrechnung/${String(s.id)}`} className="hover:underline">
                {String(s.year)} · V{String(s.version)} · {tw(`status.${String(s.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
        <HoaCreate kind="statement" ledgerId={ctx.ledger?.id} legalEntityId={ctx.entity.id} basePath={base} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{tw("meetings")}</h2>
        <ul className="text-sm">
          {(meetings.data ?? []).map((m) => (
            <li key={String(m.id)}>
              <Link href={`${base}/versammlung/${String(m.id)}`} className="hover:underline">
                {formatDateTime(String(m.scheduled_at))} · {tw(`meetingStatus.${String(m.status)}`)}
                {m.invited_at ? ` · ${tw("invitedOn", { date: formatDate(String(m.invited_at)) })}` : ""}
              </Link>
            </li>
          ))}
        </ul>
        <HoaCreate kind="meeting" legalEntityId={ctx.entity.id} basePath={base} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-medium">{t("collection")}</h2>
        <ResolutionTable rows={(resolutions.data ?? []) as never} />
      </section>
    </div>
  );
}
