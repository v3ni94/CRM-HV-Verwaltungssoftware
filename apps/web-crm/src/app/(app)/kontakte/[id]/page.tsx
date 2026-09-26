import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { CallsPanel, type CallOut } from "@/components/contacts/CallsPanel";
import { BankAccountApproval } from "@/components/contacts/BankAccountApproval";
import { ConsentsPanel } from "@/components/contacts/ConsentsPanel";
import { ContactActions } from "@/components/contacts/ContactActions";
import { NotesPanel } from "@/components/contacts/NotesPanel";
import { RelationsPanel } from "@/components/contacts/RelationsPanel";
import { RolePills } from "@/components/contacts/RolePills";
import { SepaMandatesPanel } from "@/components/contacts/SepaMandatesPanel";
import { TicketsSection, type TicketSummary } from "@/components/tickets/TicketsSection";
import { serverApi, serverFetch } from "@/lib/api-server";
import { formatDate, formatDateTime } from "@/lib/format";

import { loadContact } from "./load";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

const TABS = [
  "stammdaten",
  "kommunikation",
  "tickets",
  "bankverbindungen",
  "notizen",
  "einwilligungen",
] as const;
type Tab = (typeof TABS)[number];
const TAB_KEY: Record<Tab, string> = {
  stammdaten: "master",
  kommunikation: "communication",
  tickets: "tickets",
  bankverbindungen: "bank",
  notizen: "notes",
  einwilligungen: "consents",
};

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="grid grid-cols-3 gap-2 border-b border-border py-1.5 text-sm">
      <dt className="min-w-0 text-muted">{label}</dt>
      <dd className="col-span-2 min-w-0 break-words">{value}</dd>
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
  const tab: Tab = (TABS as readonly string[]).includes(sp.tab ?? "") ? (sp.tab as Tab) : "stammdaten";
  const contact = await loadContact(id);
  const api = serverApi();
  const me = await api.GET("/api/v1/auth/me");
  const canDelete = me.data?.permissions.includes("contacts:delete") ?? false;
  const canApproveBank = me.data?.permissions.includes("contacts:approve") ?? false;
  const currentUserId = me.data?.user_id ?? null;
  const notes =
    tab === "notizen"
      ? ((await api.GET("/api/v1/contacts/{contact_id}/notes", { params: { path: { contact_id: id } } })).data ?? [])
      : [];
  const consents =
    tab === "einwilligungen"
      ? ((await api.GET("/api/v1/contacts/{contact_id}/consents", { params: { path: { contact_id: id } } })).data ?? [])
      : [];
  const mandates =
    tab === "bankverbindungen"
      ? ((await api.GET("/api/v1/contacts/{contact_id}/sepa-mandates", { params: { path: { contact_id: id } } })).data ?? [])
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
  const relations =
    (await api.GET("/api/v1/contacts/{contact_id}/relations", { params: { path: { contact_id: id } } })).data ?? [];
  // Anrufliste (13.5, A70): typisierter BFF-Fetch, kein generierter Client nötig.
  const callsRes = tab === "kommunikation" ? await serverFetch(`/api/v1/contacts/${id}/calls`) : null;
  const calls: CallOut[] = callsRes?.ok ? ((await callsRes.json()) as CallOut[]) : [];
  const canCreateTicket = me.data?.permissions.includes("tickets:create") ?? false;
  const person = contact.kind === "person";

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
            {contact.types.length ? `, ${contact.types.map((x) => tl(`type.${x}`)).join(", ")}` : ""}
            {contact.blocked ? `, ${t("blocked")}` : ""}
          </p>
          <p className="mt-1">
            <RolePills roles={contact.roles} />
          </p>
        </div>
        <div className="ml-auto">
          <ContactActions id={contact.id} name={contact.display_name} canDelete={canDelete} />
        </div>
      </div>

      <nav aria-label={t("tabs.master")} className="flex gap-1 border-b border-border text-sm">
        {TABS.map((key) => (
          <Link
            key={key}
            href={`/kontakte/${contact.id}?tab=${key}`}
            aria-current={key === tab ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-1.5 ${key === tab ? "border-accent font-medium" : "border-transparent text-muted hover:text-fg"}`}
          >
            {t(`tabs.${TAB_KEY[key]}`)}
          </Link>
        ))}
      </nav>

      {tab === "stammdaten" ? (
        <dl>
          {person ? (
            <>
              <Row label={tf("salutation")} value={contact.salutation} />
              <Row label={tf("title")} value={contact.title} />
              <Row label={tf("firstName")} value={contact.first_name} />
              <Row label={tf("lastName")} value={contact.last_name} />
              <Row label={tf("dateOfBirth")} value={formatDate(contact.date_of_birth)} />
            </>
          ) : (
            <>
              <Row label={tf("companyName")} value={contact.company_name} />
              <Row label={tf("legalForm")} value={contact.legal_form} />
            </>
          )}
          <Row label={tf("position")} value={contact.position} />
          <Row label={tf("language")} value={contact.language} />
          <Row label={tf("preferredChannel")} value={contact.preferred_channel ? tl(`channel.${contact.preferred_channel}`) : null} />
          <Row label={tf("tags")} value={contact.tags.join(", ")} />
          <Row label={tf("notes")} value={contact.notes ? <span className="whitespace-pre-wrap">{contact.notes}</span> : null} />
          <Row label={t("created")} value={formatDateTime(contact.created_at)} />
          <Row label={t("updated")} value={formatDateTime(contact.updated_at)} />
        </dl>
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
                    {[a.postal_code, a.city].filter(Boolean).join(" ")} {a.country}
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
                    <a href={`tel:${p.number}`} className="hover:underline">
                      {p.number}
                    </a>{" "}
                    <span className="text-xs text-muted">
                      {tl(`phone.${p.label}`)}
                      {p.is_primary ? `, ${tf("primary")}` : ""}
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
                    <a href={`mailto:${e.email}`} className="hover:underline">
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
        contact.bank_accounts.length ? (
          <div className="overflow-x-auto">
            <p className="mb-2 text-xs text-muted">{t("bankApproval.hint")}</p>
<table className="w-full text-sm">
            <thead className="border-b border-border text-left text-xs text-muted">
              <tr>
                <th className="py-1 pr-3 font-medium">{tf("iban")}</th>
                <th className="py-1 pr-3 font-medium">{tf("bic")}</th>
                <th className="py-1 pr-3 font-medium">{tf("bankName")}</th>
                <th className="py-1 pr-3 font-medium">{tf("holder")}</th>
                <th className="py-1 pr-3 font-medium">{tf("validFrom")}</th>
                <th className="py-1 pr-3 font-medium">{tf("validTo")}</th>
                <th className="py-1 font-medium">{t("bankApproval.title")}</th>
              </tr>
            </thead>
            <tbody>
              {contact.bank_accounts.map((b) => (
                <tr key={b.id} className="border-b border-border">
                  <td className="py-1 pr-3 font-mono">{b.iban_masked}</td>
                  <td className="py-1 pr-3">{b.bic ?? ""}</td>
                  <td className="py-1 pr-3">{b.bank_name ?? ""}</td>
                  <td className="py-1 pr-3">{b.holder ?? ""}</td>
                  <td className="py-1 pr-3">{formatDate(b.valid_from)}</td>
                  <td className="py-1 pr-3">{formatDate(b.valid_to)}</td>
                  <td className="py-1">
                    <BankAccountApproval
                      contactId={contact.id}
                      account={b}
                      canApprove={canApproveBank}
                      currentUserId={currentUserId}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
</div>
        ) : (
          <p className="text-sm text-muted">{t("none")}</p>
        )
      ) : null}

      {tab === "bankverbindungen" ? (
        <section className="mt-4">
          <h2 className="mb-1 text-sm font-semibold">{t("sepaMandates.title")}</h2>
          <SepaMandatesPanel contactId={contact.id} mandates={mandates} />
        </section>
      ) : null}

      {tab === "tickets" ? <TicketsSection tickets={tickets as TicketSummary[]} /> : null}
      {tab === "kommunikation" ? (
        <section>
          <h2 className="mb-1 text-sm font-semibold">{t("calls.title")}</h2>
          <CallsPanel calls={calls} canCreateTicket={canCreateTicket} />
        </section>
      ) : null}
      {tab === "notizen" ? <NotesPanel contactId={contact.id} notes={notes} /> : null}
      {tab === "einwilligungen" ? <ConsentsPanel contactId={contact.id} consents={consents} /> : null}

      <RelationsPanel relations={relations} />
    </div>
  );
}
