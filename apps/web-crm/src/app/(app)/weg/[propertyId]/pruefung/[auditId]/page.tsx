import { getTranslations } from "next-intl/server";

import { AuditItemPicker } from "@/components/hoa/AuditItemPicker";
import { AuditReportsPanel, type AuditReport } from "@/components/hoa/AuditReportsPanel";
import { BoardAuditPanel, type BoardSection } from "@/components/hoa/BoardAuditPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type AuditItem = {
  id: string;
  journal_entry_id: string | null;
  document_id: string | null;
  amount: string | null;
  status: string;
  note: string | null;
  question: string | null;
  answer: string | null;
};

type Audit = {
  id: string;
  legal_entity_id: string;
  period_from: string;
  period_to: string;
  sampling: string;
  status: string;
  overall_status: string;
  outdated_reasons: Record<string, string>;
  items: AuditItem[];
};

/** Prüfauftrag (PÜ06 bis PÜ09) mit Positionsauswahl (Filter Konto, Lieferant, Datum),
 *  Prüfberichten mit Beiratsstellungnahme (A72) und dem Abschnitt Beiratszugang und
 *  Rückfragen (A52). */
export default async function AuditPage({ params }: { params: Promise<{ propertyId: string; auditId: string }> }) {
  const { propertyId, auditId } = await params;
  const [t, th] = await Promise.all([getTranslations("HoaWork"), getTranslations("Hoa")]);
  const api = serverApi();
  const [{ data, response }, boardResponse, reportsResponse] = await Promise.all([
    api.GET("/api/v1/hoa/audits/{audit_id}", { params: { path: { audit_id: auditId } } }),
    serverFetch(`/api/v1/hoa/audit-engagements/${encodeURIComponent(auditId)}/board`),
    serverFetch(`/api/v1/hoa/audits/${encodeURIComponent(auditId)}/reports`),
  ]);
  redirectIfUnauthenticated(response);
  if (!data) return <p role="alert" className={ui.alert}>{t("audit.notFound")}</p>;
  const audit = data as unknown as Audit;
  const board = boardResponse.ok ? ((await boardResponse.json()) as BoardSection) : null;
  const reports = reportsResponse.ok ? ((await reportsResponse.json()) as AuditReport[]) : [];
  // Accounts of the community ledger for the account filter of the position picker (PÜ08).
  const ledgers = await api.GET("/api/v1/accounting/ledgers");
  const ledger = (ledgers.data ?? []).find((l) => l.legal_entity_id === audit.legal_entity_id) ?? null;
  const accountRows = ledger
    ? await api.GET("/api/v1/accounting/ledgers/{ledger_id}/accounts", { params: { path: { ledger_id: ledger.id } } })
    : null;
  const accounts = ((accountRows?.data ?? []) as { id: string; number: string; name: string }[]).map((a) => ({
    id: a.id,
    number: a.number,
    name: a.name,
  }));
  // Names of the auditor contacts (data minimisation: name only).
  const names = new Map<string, string>();
  for (const contactId of board?.auditor_contact_ids ?? []) {
    const name = await api.GET("/api/v1/contacts/{contact_id}/name", { params: { path: { contact_id: contactId } } });
    if (name.data?.display_name) names.set(contactId, String(name.data.display_name));
  }
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        breadcrumb={[
          { href: "/weg", label: th("title") },
          { href: `/weg/${propertyId}`, label: t("audits") },
        ]}
        title={`${t("audit.title")} · ${t(`audit.sampling.${audit.sampling}`)}`}
      />
      <p className={ui.notice}>
        {t("audit.overallStatus")}: {t.has(`audit.itemStatus.${audit.overall_status}`) ? t(`audit.itemStatus.${audit.overall_status}`) : t.has(`audit.status.${audit.overall_status}`) ? t(`audit.status.${audit.overall_status}`) : audit.overall_status}
      </p>
      <section className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("audit.items")}</h2>
        {audit.items.length === 0 ? <p className="text-sm text-muted">{t("audit.noItems")}</p> : null}
        <div className="overflow-x-auto">
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("audit.item")}</th>
              <th>{t("audit.statusLabel")}</th>
              <th className="text-right">{t("amount")}</th>
              <th>{t("audit.note")}</th>
            </tr>
          </thead>
          <tbody>
            {audit.items.map((item, index) => (
              <tr key={item.id}>
                <td>{t("audit.itemNumber", { n: index + 1 })}</td>
                <td>
                  {t(`audit.itemStatus.${item.status}`)}
                  {audit.outdated_reasons[item.id] ? ` (${audit.outdated_reasons[item.id]})` : ""}
                </td>
                <td className="text-right">{item.amount ? formatEur(item.amount) : ""}</td>
                <td>{[item.note, item.question, item.answer].filter(Boolean).join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section>
      <AuditItemPicker auditId={auditId} accounts={accounts} periodFrom={audit.period_from} periodTo={audit.period_to} />
      <AuditReportsPanel auditId={auditId} reports={reports} />
      {board ? (
        <BoardAuditPanel
          auditId={auditId}
          section={board}
          items={audit.items.map((item, index) => ({ id: item.id, label: t("audit.itemNumber", { n: index + 1 }) }))}
          contactNames={Object.fromEntries(names)}
        />
      ) : null}
    </div>
  );
}
