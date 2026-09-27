import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { PropertyBankAccounts } from "@/components/banking/PropertyBankAccounts";
import { AuditLogPanel } from "@/components/common/AuditLogPanel";
import { EntityLinksBar } from "@/components/common/EntityLinksBar";
import { DmsDocumentsPanel } from "@/components/documents/DmsDocumentsPanel";
import { PropertyMeteringTab } from "@/components/metering/PropertyMeteringTab";
import { CompletenessPanel } from "@/components/objektakte/CompletenessPanel";
import { LegalEntityBankAccounts } from "@/components/properties/LegalEntityBankAccounts";
import { PropertyMasterData, type PropertyMaster } from "@/components/properties/PropertyMasterData";
import { PropertyOwnerPanel, type CurrentOwner } from "@/components/properties/PropertyOwnerPanel";
import { PropertyTermination, type Termination } from "@/components/properties/PropertyTermination";
import { PropertyNotices } from "@/components/properties/PropertyNotices";
import {
  BillingPeriodsPanel,
  BuildingsPanel,
  PortalDocumentsPanel,
  ServiceProvidersPanel,
  SubCommunitiesPanel,
  type BillingPeriodRow,
  type BuildingRow,
  type PortalDocumentRow,
  type ProviderRow,
  type SubCommunityRow,
} from "@/components/properties/PropertyPanels";
import { UnitsTable } from "@/components/properties/UnitsTable";
import { TicketsSection, type TicketSummary } from "@/components/tickets/TicketsSection";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusChip } from "@/components/ui/StatusChip";
import { redirectIfUnauthenticated, serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { problemMessage, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

type BankAccountRow = { id: string; kind: string; holder: string; iban_masked: string; bank_name: string | null; ledger_account_id: string | null };

/** Plain fetch of a list: typed api.GET calls beyond a handful exceed the TypeScript
 *  instantiation depth on this page; a failed call yields an empty list, not an error page. */
async function load<T>(path: string, fallback: T): Promise<T> {
  const response = await serverFetch(path);
  return response.ok ? ((await response.json()) as T) : fallback;
}

/** Sachkontenbezeichnungen (Nummer und Name) aller Buchungskreise des Objekts. */
async function accountLabels(propertyId: string): Promise<{ ledgerId: string | null; labels: Map<string, string> }> {
  const ledgers = await load<{ id: string }[]>(`/api/v1/ledgers?property_id=${propertyId}`, []);
  const labels = new Map<string, string>();
  await Promise.all(
    ledgers.map(async (ledger) => {
      for (const a of await load<{ id: string; number: string; name: string }[]>(`/api/v1/ledgers/${ledger.id}/accounts`, [])) {
        labels.set(a.id, `${a.number} ${a.name}`);
      }
    }),
  );
  return { ledgerId: ledgers[0]?.id ?? null, labels };
}

async function contactNames(ids: (string | null | undefined)[]): Promise<Map<string, string>> {
  const names = new Map<string, string>();
  await Promise.all(
    [...new Set(ids.filter((id): id is string => Boolean(id)))].map(async (id) => {
      const contact = await load<{ display_name?: string } | null>(`/api/v1/contacts/${id}`, null);
      if (contact?.display_name) names.set(id, contact.display_name);
    }),
  );
  return names;
}

export default async function PropertyPage({ params }: { params: Promise<{ propertyId: string }> }) {
  const { propertyId } = await params;
  const t = await getTranslations("Properties");
  const api = serverApi();
  const path = { params: { path: { property_id: propertyId } } };
  const [{ data, error, response }, units, contacts, maintenance] = await Promise.all([
    api.GET("/api/v1/properties/{property_id}", path),
    api.GET("/api/v1/properties/{property_id}/units", { params: { path: { property_id: propertyId }, query: { with_occupants: true } } }),
    api.GET("/api/v1/properties/{property_id}/contacts", path),
    api.GET("/api/v1/properties/{property_id}/maintenance", path),
  ]);
  redirectIfUnauthenticated(response);
  const [tickets, me] = await Promise.all([
    api.GET("/api/v1/tickets", { params: { query: { property_id: propertyId, limit: 50, include_closed: true } } }),
    getMe(),
  ]);
  const base = `/api/v1/properties/${propertyId}`;
  const [owners, buildings, periods, subCommunities, portalDocuments, providers, bankAccounts, accounts, termination] = await Promise.all([
    load<CurrentOwner[]>(`${base}/owners`, []),
    load<BuildingRow[]>(`${base}/buildings`, []),
    load<BillingPeriodRow[]>(`${base}/billing-periods`, []),
    load<SubCommunityRow[]>(`${base}/sub-communities`, []),
    load<PortalDocumentRow[]>(`${base}/portal-documents`, []),
    load<ProviderRow[]>(`${base}/service-providers`, []),
    load<BankAccountRow[]>(`${base}/bank-accounts`, []),
    accountLabels(propertyId),
    load<Termination | null>(`${base}/termination`, null),
  ]);
  const names = await contactNames([...providers.map((p) => p.contact_id), ...owners.map((o) => o.tax_advisor_contact_id)]);
  if (!data) {
    return (
      <p role="alert" className={ui.alert}>
        {problemMessage(error as Problem | undefined, response.status)}
      </p>
    );
  }
  const address = [[data.street, data.house_number].filter(Boolean).join(" "), [data.postal_code, data.city].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
  const unitRows = units.data ?? [];
  const isHoa = data.management_type !== "rental";
  const openMaintenance = (maintenance.data ?? []).filter((m) => m.status === "open");
  const canEdit = me.data?.permissions.includes("properties:update") ?? false;
  const isSuperadmin = me.data?.is_superadmin ?? false;
  const ownerRows = owners.map((o) => ({
    ...o,
    clearing_account_label: o.clearing_account_id ? (accounts.labels.get(o.clearing_account_id) ?? null) : null,
    tax_advisor_name: o.tax_advisor_contact_id ? (names.get(o.tax_advisor_contact_id) ?? null) : null,
  }));
  const providerRows = providers.map((p) => ({
    ...p,
    contact_name: names.get(p.contact_id) ?? null,
    creditor_account_label: p.creditor_account_id ? (accounts.labels.get(p.creditor_account_id) ?? null) : null,
  }));
  const ticketRows = (tickets.data ?? []) as TicketSummary[];
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumb={[{ href: "/objekte", label: t("title") }, { label: data.number }]}
        title={data.name}
        action={
          <div className="flex flex-wrap gap-2">
            {isHoa ? (
              <Link href={`/weg/${propertyId}`} className={ui.primary}>
                {t("toHoa")}
              </Link>
            ) : null}
            <Link href="/vermietung" className={ui.button}>
              {t("toLetting")}
            </Link>
          </div>
        }
      />
      <EntityLinksBar
        links={[
          { type: "unit", href: "#einheiten", count: unitRows.length, label: t("units") },
          { type: "contract", href: `/vertraege?property_id=${propertyId}` },
          { type: "contact", href: "#kontakte", count: (contacts.data ?? []).length, label: t("contacts") },
          { type: "ticket", href: `/tickets?property_id=${propertyId}`, count: ticketRows.length },
          { type: "ledger", id: accounts.ledgerId },
        ]}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("statusLabel")}</p>
          <p className="mt-1">
            <StatusChip domain="property" status={data.status} />
          </p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("type")}</p>
          <p className="mt-1 text-sm">{t(`managementType.${data.management_type}`)}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("address")}</p>
          <p className="mt-1 text-sm">{address || t("noAddress")}</p>
        </div>
        <div className={ui.card}>
          <p className={ui.subtitle}>{t("units")}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{unitRows.length}</p>
        </div>
      </div>

      <PropertyTermination propertyId={propertyId} status={data.status} termination={termination} canEdit={canEdit} isSuperadmin={isSuperadmin} />

      <PropertyMasterData property={data as unknown as PropertyMaster} canEdit={canEdit && data.status !== "terminated"} />

      {(data.legal_entities ?? []).length ? (
        <section className={ui.card}>
          <h2 className={ui.subtitle}>{t("legalEntities")}</h2>
          <ul className="mt-2 flex flex-wrap gap-2 text-sm">
            {(data.legal_entities ?? []).map((e) => (
              <li key={e.id} className={ui.badgeGold}>
                {t(`entityKind.${e.kind}`)}: {e.name}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <PropertyOwnerPanel propertyId={propertyId} managementType={data.management_type} owners={ownerRows} canEdit={canEdit} />

      <BuildingsPanel buildings={buildings} />

      <section id="einheiten" className="flex flex-col gap-2">
        <h2 className={ui.h2}>{t("units")}</h2>
        {unitRows.length === 0 ? (
          <p className="text-sm text-muted">{t("noUnits")}</p>
        ) : (
          <UnitsTable units={unitRows} />
        )}
      </section>

      {isHoa ? <SubCommunitiesPanel rows={subCommunities} /> : null}
      <BillingPeriodsPanel periods={periods} />

      <div className="grid gap-4 md:grid-cols-2">
        <section id="kontakte" className={ui.card}>
          <h2 className={ui.subtitle}>{t("contacts")}</h2>
          {(contacts.data ?? []).length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("noContacts")}</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {(contacts.data ?? []).map((c) => (
                <li key={c.id}>
                  <Link href={`/kontakte/${c.contact_id}`} className="hover:underline">
                    {c.category_code}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className={ui.card}>
          <h2 className={ui.subtitle}>{t("maintenanceOpen")}</h2>
          {openMaintenance.length === 0 ? (
            <p className="mt-2 text-sm text-muted">{t("noMaintenance")}</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {openMaintenance.map((m) => (
                <li key={m.id} className="flex justify-between gap-2">
                  <span>{m.title}</span>
                  <span className="tabular-nums text-muted">{m.due_date ?? ""}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <ServiceProvidersPanel rows={providerRows} />

      <PropertyBankAccounts propertyId={propertyId} legalEntities={(data.legal_entities ?? []).map((e) => ({ id: e.id, kind: e.kind, name: e.name }))} />
      <LegalEntityBankAccounts
        propertyId={propertyId}
        legalEntities={(data.legal_entities ?? []).map((e) => ({ id: e.id, kind: e.kind, name: e.name }))}
        canEdit={canEdit}
      />
      {bankAccounts.length ? (
        <section className={ui.card} data-testid="property-bank-ledger">
          <h2 className={ui.subtitle}>{t("bankAccountsLedger")}</h2>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {bankAccounts.map((a) => (
              <li key={a.id} className="flex flex-wrap gap-x-3">
                <span className="font-medium">{a.holder}</span>
                <span className="text-muted">{a.iban_masked}</span>
                <span>{a.ledger_account_id ? (accounts.labels.get(a.ledger_account_id) ?? a.ledger_account_id) : <span className="text-muted">{t("bankAccountsNoLedger")}</span>}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <DmsDocumentsPanel entity="property" id={propertyId} />
      <PortalDocumentsPanel rows={portalDocuments} />
      <PropertyNotices propertyId={propertyId} />
      <PropertyMeteringTab property={{ id: data.id, number: data.number, name: data.name, street: data.street, house_number: data.house_number, postal_code: data.postal_code, city: data.city }} permissions={me.data?.permissions ?? []} />
      <CompletenessPanel propertyId={propertyId} />
      <TicketsSection tickets={ticketRows} />
      <AuditLogPanel entityType="property" entityId={propertyId} />
    </div>
  );
}
