import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { EntityLinksBar, type EntityLink } from "@/components/common/EntityLinksBar";
import { LexofficeContactBadge, LexofficeContactSection } from "@/components/lexoffice/LexofficeContactStatus";
import { CallsPanel, type CallOut } from "@/components/contacts/CallsPanel";
import { BankAccountsSection } from "@/components/contacts/BankAccountsSection";
import { ConsentsPanel } from "@/components/contacts/ConsentsPanel";
import { ContactActions } from "@/components/contacts/ContactActions";
import { ContactMasterData } from "@/components/contacts/ContactMasterData";
import { ContactQuickActions } from "@/components/contacts/ContactQuickActions";
import { CreditorPropertiesSection, type CreditorProperty } from "@/components/contacts/CreditorPropertiesSection";
import { NotesPanel } from "@/components/contacts/NotesPanel";
import { PortalAccessSection } from "@/components/contacts/PortalAccessSection";
import { PortalProposalsPanel } from "@/components/contacts/PortalProposalsPanel";
import { RelationsPanel } from "@/components/contacts/RelationsPanel";
import { RepresentativesPanel } from "@/components/contacts/RepresentativesPanel";
import { RolePills } from "@/components/contacts/RolePills";
import { SepaMandatesPanel } from "@/components/contacts/SepaMandatesPanel";
import {
  TicketsSection,
  type TicketSummary,
} from "@/components/tickets/TicketsSection";
import { serverApi, serverFetch } from "@/lib/api-server";
import { getMe } from "@/lib/me";
import { formatDate, formatDateTime } from "@/lib/format";

import { loadContact } from "./load";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

// Tabs of section 4.1 (Masterprompt Ergänzung): Übersicht, Beziehungen, Konten, Nachrichten,
// Dokumente, Tickets, Portal-Freigaben, Notizen, Ereignisprotokoll (plus Einwilligungen).
const TABS = [
  "stammdaten",
  "beziehungen",
  "kommunikation",
  "tickets",
  "bankverbindungen",
  "dokumente",
  "freigaben",
  "notizen",
  "einwilligungen",
  "protokoll",
] as const;
type Tab = (typeof TABS)[number];
const TAB_KEY: Record<Tab, string> = {
  stammdaten: "master",
  beziehungen: "relations",
  kommunikation: "communication",
  tickets: "tickets",
  bankverbindungen: "bank",
  dokumente: "documents",
  freigaben: "releases",
  notizen: "notes",
  einwilligungen: "consents",
  protokoll: "log",
};

type AuditEntry = {
  id: string;
  entity_type: string;
  changes: Record<string, unknown>;
  actor_user_id: string | null;
  occurred_at: string;
};

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="grid grid-cols-1 gap-2 border-b border-border py-1.5 text-sm sm:grid-cols-3">
      <dt className="min-w-0 text-muted">{label}</dt>
      <dd className="min-w-0 break-words sm:col-span-2">{value}</dd>
    </div>
  );
}

export default async function ContactDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const [{ id }, sp, t, tf, tl] = await Promise.all([
    params,
    searchParams,
    getTranslations("Contacts"),
    getTranslations("ContactForm"),
    getTranslations("Labels"),
  ]);
  const tab: Tab = (TABS as readonly string[]).includes(sp.tab ?? "")
    ? (sp.tab as Tab)
    : "stammdaten";
  const contact = await loadContact(id);
  const api = serverApi();
  const me = await getMe();
  const canDelete = me.data?.permissions.includes("contacts:delete") ?? false;
  const canApproveBank =
    me.data?.permissions.includes("contacts:approve") ?? false;
  const currentUserId = me.data?.user_id ?? null;
  const isPlatformAdmin = me.data?.is_platform_admin ?? false;
  const canInvitePortal =
    me.data?.permissions.includes("contacts:update") ?? false;
  const canDismissCall =
    me.data?.permissions.includes("communication:update") ?? false;
  const notes =
    tab === "notizen"
      ? ((
          await api.GET("/api/v1/contacts/{contact_id}/notes", {
            params: { path: { contact_id: id } },
          })
        ).data ?? [])
      : [];
  const consents =
    tab === "einwilligungen"
      ? ((
          await api.GET("/api/v1/contacts/{contact_id}/consents", {
            params: { path: { contact_id: id } },
          })
        ).data ?? [])
      : [];
  const mandates =
    tab === "bankverbindungen"
      ? ((
          await api.GET("/api/v1/contacts/{contact_id}/sepa-mandates", {
            params: { path: { contact_id: id } },
          })
        ).data ?? [])
      : [];
  // Personal tickets: linked contact or initiator (any_contact_id), deduplicated by id.
  const tickets =
    tab === "tickets"
      ? [
          ...new Map(
            ((await api.GET("/api/v1/tickets", { params: { query: { any_contact_id: id, limit: 100, include_closed: true } } })).data ?? []).map(
              (x) => [String((x as { id: unknown }).id), x],
            ),
          ).values(),
        ]
      : [];
  // Relations feed the tab and the link bar (Ergänzung 5): properties, units and contracts.
  const relations = (await api.GET("/api/v1/contacts/{contact_id}/relations", { params: { path: { contact_id: id } } })).data ?? [];
  const uniqueLinks = (type: EntityLink["type"], key: "property_id" | "unit_id" | "contract_id", label: (r: (typeof relations)[number]) => string | null) => {
    const seen = new Set<string>();
    return relations.flatMap((r) => {
      const value = r[key];
      if (!value || seen.has(value)) return [];
      seen.add(value);
      return [{ type, id: value, label: label(r) } satisfies EntityLink];
    });
  };
  const entityLinks: EntityLink[] = [
    ...uniqueLinks("property", "property_id", (r) => r.property_name),
    ...uniqueLinks("unit", "unit_id", (r) => r.unit_label ?? null),
    ...uniqueLinks("contract", "contract_id", () => null),
    { type: "ticket", href: `/tickets?contact_id=${contact.id}`, label: t("links.tickets") },
  ];
  // Authorised representatives with delivery rule (operator decision 26.09.2026).
  const contactRelations =
    tab === "beziehungen"
      ? ((await api.GET("/api/v1/contacts/{contact_id}/contact-relations", { params: { path: { contact_id: id } } })).data ?? [])
      : [];
  // Objekte als Dienstleister (Regel M11-08): nur für Kreditoren (Rolle dienstleister).
  const creditorRes =
    tab === "beziehungen" && contact.roles.includes("dienstleister")
      ? await serverFetch(`/api/v1/contacts/${id}/creditor-properties`)
      : null;
  const creditorProperties: CreditorProperty[] = creditorRes?.ok ? ((await creditorRes.json()) as CreditorProperty[]) : [];
  // Dokumente (4.1): documents linked to the contact.
  const documents =
    tab === "dokumente"
      ? ((await api.GET("/api/v1/documents", { params: { query: { entity_type: "contact", entity_id: id, page_size: 100 } } })).data?.items ?? [])
      : [];
  // Ereignisprotokoll (4.1): audit entries of this record; needs audit:read, otherwise empty.
  const auditRes = tab === "protokoll" ? await serverFetch(`/api/v1/tenant/audit-log?entity_id=${id}`) : null;
  const auditEntries: AuditEntry[] = auditRes?.ok ? ((await auditRes.json()) as AuditEntry[]) : [];
  const canReadAudit = me.data?.permissions.includes("audit:read") ?? false;
  const canEditRelations =
    me.data?.permissions.includes("contacts:update") ?? false;
  const canEditMaster = canEditRelations;
  // Anrufliste (13.5, A70): typisierter BFF-Fetch, kein generierter Client nötig.
  const callsRes =
    tab === "kommunikation"
      ? await serverFetch(`/api/v1/contacts/${id}/calls`)
      : null;
  const calls: CallOut[] = callsRes?.ok
    ? ((await callsRes.json()) as CallOut[])
    : [];
  const canCreateTicket =
    me.data?.permissions.includes("tickets:create") ?? false;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start gap-3">
        <div>
          <Link href="/kontakte" className="text-xs text-muted hover:underline">
            {t("back")}
          </Link>
          <h1 className={ui.title}>{contact.display_name}</h1>
          <p className="text-xs text-muted">
            {tl(`kind.${contact.kind}`)}
            {contact.types.length
              ? `, ${contact.types.map((x) => tl(`type.${x}`)).join(", ")}`
              : ""}
            {contact.blocked ? `, ${t("blocked")}` : ""}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-2">
            <RolePills roles={contact.roles} />
            <LexofficeContactBadge contactId={contact.id} />
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto">
          <ContactQuickActions
            phone={(contact.phones.find((p) => p.is_primary) ?? contact.phones[0])?.number}
            email={(contact.emails.find((e) => e.is_primary) ?? contact.emails[0])?.email}
          />
          <ContactActions
            id={contact.id}
            name={contact.display_name}
            canDelete={canDelete}
          />
        </div>
      </div>

      <EntityLinksBar links={entityLinks} />

      {/* One swipeable row on phones, wrapping from sm (M31, ui.tabBar); the server page renders
       *  only class names, no client hooks. */}
      <nav aria-label={t("tabs.master")} className={`${ui.tabBar} border-b border-border pb-1`} data-testid="contact-tabs">
        {TABS.map((key) => (
          <Link
            key={key}
            href={`/kontakte/${contact.id}?tab=${key}`}
            aria-current={key === tab ? "page" : undefined}
            className={key === tab ? ui.tabActive : ui.tab}
          >
            {t(`tabs.${TAB_KEY[key]}`)}
          </Link>
        ))}
      </nav>

      {tab === "stammdaten" ? (
        <>
        <ContactMasterData contact={contact} canEdit={canEditMaster} />
        <h2 className="text-sm font-semibold">{t("masterData.readOnly")}</h2>
        <dl>
          <Row label={tf("tags")} value={contact.tags.join(", ")} />
          <Row
            label={tf("dates")}
            value={
              contact.dates?.length
                ? contact.dates
                    .map((d) => `${tf(`dateKind.${d.kind}`)}: ${formatDate(d.date)}${d.note ? ` (${d.note})` : ""}`)
                    .join(", ")
                : null
            }
          />
          <Row label={t("blockedAt")} value={formatDateTime(contact.blocked_at)} />
          <Row
            label={t("deleteAfter")}
            value={
              contact.delete_after ? (
                <>
                  {formatDate(contact.delete_after)}
                  <span className="block text-xs text-muted">{t("deleteAfterHint")}</span>
                </>
              ) : null
            }
          />
          <Row
            label={t("created")}
            value={formatDateTime(contact.created_at)}
          />
          <Row
            label={t("updated")}
            value={formatDateTime(contact.updated_at)}
          />
        </dl>
        <LexofficeContactSection
          contactId={contact.id}
          contactName={contact.display_name}
          canUpdate={canEditRelations}
          canCreateDraft={me.data?.permissions.includes("accounting:create") ?? false}
        />
        </>
      ) : null}

      {tab === "kommunikation" ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <section>
            <h2 className="mb-1 text-sm font-semibold">{tf("addresses")}</h2>
            {contact.addresses.length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {contact.addresses.map((a) => (
                  <li key={a.id}>
                    <span className="text-xs text-muted">
                      {tl(`address.${a.label ?? "postal"}`)}
                      {a.is_primary ? `, ${tf("primary")}` : ""}
                    </span>
                    <br />
                    {[a.street, a.house_number].filter(Boolean).join(" ")}
                    {a.addition ? <>, {a.addition}</> : null}
                    <br />
                    {[a.postal_code, a.city].filter(Boolean).join(" ")}{" "}
                    {a.country}
                    {a.state ? <>, {a.state}</> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">{t("none")}</p>
            )}
          </section>
          <section>
            <h2 className="mb-1 text-sm font-semibold">{tf("phones")}</h2>
            {contact.phones.length ? (
              <ul className="text-sm">
                {contact.phones.map((p) => (
                  <li key={p.id}>
                    <a href={`tel:${p.number.replace(/\s+/g, "")}`} className="inline-flex min-h-11 items-center hover:underline">
                      {p.number}
                    </a>{" "}
                    <span className="text-xs text-muted">
                      {tl(`phone.${p.label}`)}
                      {p.is_primary ? `, ${tf("primary")}` : ""}
                      {p.country_code || p.area_code ? `, ${[p.country_code, p.area_code].filter(Boolean).join(" ")}` : ""}
                      {p.note ? `, ${p.note}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">{t("none")}</p>
            )}
          </section>
          <section>
            <h2 className="mb-1 text-sm font-semibold">{tf("emails")}</h2>
            {contact.emails.length ? (
              <ul className="text-sm">
                {contact.emails.map((e) => (
                  <li key={e.id}>
                    <a href={`mailto:${e.email}`} className="inline-flex min-h-11 items-center break-all hover:underline">
                      {e.email}
                    </a>{" "}
                    <span className="text-xs text-muted">
                      {e.label}
                      {e.is_primary ? `, ${tf("primary")}` : ""}
                      {e.is_portal_login ? `, ${tf("portalLogin")}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">{t("none")}</p>
            )}
          </section>
        </div>
      ) : null}

      {tab === "bankverbindungen" ? (
        <BankAccountsSection
          contactId={contact.id}
          accounts={contact.bank_accounts}
          canEdit={canEditMaster}
          canApprove={canApproveBank}
          currentUserId={currentUserId}
          isPlatformAdmin={isPlatformAdmin}
        />
      ) : null}

      {tab === "bankverbindungen" ? (
        <section className="mt-4">
          <h2 className="mb-1 text-sm font-semibold">
            {t("sepaMandates.title")}
          </h2>
          <SepaMandatesPanel contactId={contact.id} mandates={mandates} />
        </section>
      ) : null}

      {tab === "tickets" ? <TicketsSection tickets={tickets as TicketSummary[]} /> : null}
      {tab === "freigaben" ? (
        <PortalAccessSection
          contactId={contact.id}
          displayName={contact.display_name}
          emails={contact.emails}
          canInvite={canInvitePortal}
        />
      ) : null}
      {tab === "freigaben" ? (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t("portalProposals.title")}</h2>
          <PortalProposalsPanel contactId={contact.id} canDecide={canInvitePortal} />
        </section>
      ) : null}
      {tab === "kommunikation" ? (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t("calls.title")}</h2>
          <CallsPanel
            calls={calls}
            canCreateTicket={canCreateTicket}
            canDismiss={canDismissCall}
          />
        </section>
      ) : null}
      {tab === "notizen" ? <NotesPanel contactId={contact.id} notes={notes} /> : null}
      {tab === "einwilligungen" ? <ConsentsPanel contactId={contact.id} consents={consents} /> : null}

      {tab === "beziehungen" ? (
        <>
          <RelationsPanel relations={relations} />
          {contact.roles.includes("dienstleister") ? <CreditorPropertiesSection rows={creditorProperties} /> : null}
          <RepresentativesPanel
            contactId={contact.id}
            relations={contactRelations}
            canEdit={canEditRelations}
          />
        </>
      ) : null}
      {tab === "dokumente" ? (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t("documents.title")}</h2>
          {documents.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {documents.map((d) => (
                <li key={d.id}>
                  <Link href={`/dokumente/${d.id}`} className="hover:underline">
                    {d.title}
                  </Link>{" "}
                  <span className="text-xs text-muted">
                    {formatDateTime(d.created_at)}
                    {d.is_draft ? `, ${t("documents.draft")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("none")}</p>
          )}
        </section>
      ) : null}
      {tab === "protokoll" ? (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t("log.title")}</h2>
          {!canReadAudit ? (
            <p className="text-sm text-muted">{t("log.noPermission")}</p>
          ) : auditEntries.length ? (
            <ul className="flex flex-col gap-2 text-sm" data-testid="contact-audit-log">
              {auditEntries.map((entry) => (
                <li key={entry.id} className={ui.card}>
                  <p className="text-xs text-muted">
                    {formatDateTime(entry.occurred_at)}
                    {entry.actor_user_id ? `, ${t("log.actor")} ${entry.actor_user_id}` : ""}
                  </p>
                  <p>{Object.keys(entry.changes).join(", ") || t("log.noFields")}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("none")}</p>
          )}
        </section>
      ) : null}
    </div>
  );
}
