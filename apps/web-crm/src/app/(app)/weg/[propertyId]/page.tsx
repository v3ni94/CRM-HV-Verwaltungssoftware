import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { AuditCreateForm } from "@/components/hoa/AuditCreateForm";
import { FinanceCreate } from "@/components/hoa/FinanceForms";
import { HoaCreate } from "@/components/hoa/HoaForms";
import { LevyCreate } from "@/components/hoa/LevyForms";
import { ResolutionTable } from "@/components/hoa/ResolutionTable";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverFetch } from "@/lib/api-server";
import { formatDate, formatDateTime } from "@/lib/format";
import { hoaContext } from "@/lib/hoa";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function HoaDetailPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const [t, tw, tf] = await Promise.all([getTranslations("Hoa"), getTranslations("HoaWork"), getTranslations("HoaFinance")]);
  const ctx = await hoaContext(propertyId);
  redirectIfUnauthenticated(ctx.response);
  if (!ctx.property) return <p role="alert" className={ui.alert}>{t("noEntity")}</p>;
  const base = `/weg/${propertyId}`;
  if (!ctx.entity) return <p className="text-sm text-muted">{t("noEntity")}</p>;
  const [resolutions, plans, statements, meetings, levies, auditsResponse] = await Promise.all([
    ctx.api.GET("/api/v1/hoa/resolutions", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.ledger ? ctx.api.GET("/api/v1/hoa/plans", { params: { query: { ledger_id: ctx.ledger.id } } }) : null,
    ctx.ledger ? ctx.api.GET("/api/v1/hoa/statements", { params: { query: { ledger_id: ctx.ledger.id } } }) : null,
    ctx.api.GET("/api/v1/hoa/meetings", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.api.GET("/api/v1/hoa/special-levies", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    serverFetch(`/api/v1/hoa/audits?legal_entity_id=${encodeURIComponent(ctx.entity.id)}`),
  ]);
  // Beiratsprüfungen (PÜ06, A52, A72): list and creation form; positions are selected on the
  // engagement page with the filters of PÜ08.
  const audits = auditsResponse.ok
    ? ((await auditsResponse.json()) as { id: string; period_from: string; period_to: string; purpose: string; status: string }[])
    : [];
  // Darlehen, Versicherungsfälle, Maßnahmen (W10, A59): recording and evidence, no posting.
  const [loans, claims, measures, accounts] = await Promise.all([
    ctx.api.GET("/api/v1/hoa/loans", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.api.GET("/api/v1/hoa/insurance-claims", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.api.GET("/api/v1/hoa/measures", { params: { query: { legal_entity_id: ctx.entity.id } } }),
    ctx.ledger ? ctx.api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: ctx.ledger.id } } }) : null,
  ]);
  const allAccounts = (accounts?.data ?? []) as { id: string; number: string; name: string; category: string }[];
  const loanAccounts = allAccounts.filter((a) => a.category === "loan").map((a) => ({ id: a.id, number: a.number, name: a.name }));
  // A79: resolutions of the community for the claim form (structured link).
  const claimResolutions = ((resolutions.data ?? []) as { id: string; number?: number | null; decided_on: string; subject: string }[]).map((r) => ({ id: String(r.id), number: r.number ?? null, decided_on: formatDate(String(r.decided_on)), subject: String(r.subject) }));
  const expenseAccounts = allAccounts.filter((a) => a.category === "expense").map((a) => ({ id: a.id, number: a.number, name: a.name }));
  const statementOptions = (statements?.data ?? []).map((s) => ({
    id: String(s.id),
    label: `${String(s.year)} · V${String(s.version)} · ${tw(`status.${String(s.status)}`)}`,
  }));
  const finance = [
    { kind: "loan" as const, title: tf("loans"), path: "darlehen", rows: (loans.data ?? []).map((l) => ({ id: String(l.id), label: `${String(l.lender)} · ${tf(`loanStatus.${String(l.status)}`)}` })) },
    { kind: "claim" as const, title: tf("claims"), path: "versicherung", rows: (claims.data ?? []).map((c) => ({ id: String(c.id), label: `${String(c.title)} · ${tf(`claimStatus.${String(c.status)}`)}` })) },
    { kind: "measure" as const, title: tf("measures"), path: "massnahme", rows: (measures.data ?? []).map((m) => ({ id: String(m.id), label: `${String(m.title)} · ${tf(`measureStatus.${String(m.status)}`)}` })) },
  ];
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        breadcrumb={[{ href: "/weg", label: t("title") }]}
        title={`${ctx.property.number} ${ctx.property.name}`}
      />
      <p className={ui.notice}>{t("gateNotice")}</p>
      {!ctx.ledger ? <p className="text-sm text-muted">{tw("noLedger")}</p> : null}
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tw("plans")}</h2>
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
        <h2 className={ui.h2}>{tw("statements")}</h2>
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
        <h2 className={ui.h2}>{tw("meetings")}</h2>
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
        <h2 className={ui.h2}>{tw("inspection")}</h2>
        <Link href={`${base}/einsicht`} className="text-sm hover:underline">
          {tw("inspectionLink")}
        </Link>
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tw("levies")}</h2>
        <ul className="text-sm">
          {(levies.data ?? []).map((l) => (
            <li key={String(l.id)}>
              <Link href={`${base}/sonderumlage/${String(l.id)}`} className="hover:underline">
                {String(l.purpose)} · {tw(`levyStatus.${String(l.status)}`)}
              </Link>
            </li>
          ))}
        </ul>
        {ctx.ledger ? <LevyCreate ledgerId={ctx.ledger.id} keys={ctx.keys} basePath={base} /> : null}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{tw("audits")}</h2>
        {audits.length === 0 ? <p className="text-sm text-muted">{tw("audit.none")}</p> : null}
        <ul className="text-sm">
          {audits.map((a) => (
            <li key={a.id}>
              <Link href={`${base}/pruefung/${a.id}`} className="hover:underline">
                {formatDate(a.period_from)} bis {formatDate(a.period_to)} · {a.purpose} · {tw(`audit.status.${a.status}`)}
              </Link>
            </li>
          ))}
        </ul>
        <AuditCreateForm legalEntityId={ctx.entity.id} statements={statementOptions} accounts={expenseAccounts} basePath={base} />
      </section>
      {finance.map((sec) => (
        <section key={sec.kind} className="flex flex-col gap-2" data-testid={`hoa-${sec.kind}s`}>
          <h2 className={ui.h2}>{sec.title}</h2>
          <ul className="text-sm">
            {sec.rows.map((r) => (
              <li key={r.id}>
                <Link href={`${base}/${sec.path}/${r.id}`} className="hover:underline">
                  {r.label}
                </Link>
              </li>
            ))}
          </ul>
          {ctx.ledger ? <FinanceCreate kind={sec.kind} ledgerId={ctx.ledger.id} basePath={base} loanAccounts={loanAccounts} resolutions={sec.kind === "claim" ? claimResolutions : []} /> : null}
        </section>
      ))}
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("collection")}</h2>
        <ResolutionTable rows={(resolutions.data ?? []) as never} />
      </section>
    </div>
  );
}
