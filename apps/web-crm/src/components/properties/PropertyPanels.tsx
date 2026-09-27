"use client";
/** Lesende Abschnitte der Objektseite für die Daten aus AP2 (Gebäude, Abrechnungszeiträume,
 *  Untergemeinschaften, Objektmappe, Dienstleister). Die Daten kommen serverseitig aus den
 *  Listen-Endpunkten; Anlage und Änderung laufen weiter über die bestehenden Formulare und
 *  die API. */
import Link from "next/link";
import { useTranslations } from "next-intl";

import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type BuildingRow = {
  id: string;
  property_id: string;
  name: string;
  street?: string | null;
  house_number?: string | null;
  address_addition?: string | null;
  construction_year?: number | null;
  floors?: number | null;
  energy_certificate_type?: string | null;
  energy_certificate_class?: string | null;
  energy_certificate_valid_until?: string | null;
};

export type BillingPeriodRow = { id: string; kind: string; valid_from: string; valid_to: string; board_online_audit: boolean; notes?: string | null };
export type SubCommunityRow = { id: string; code: string; name: string; notes?: string | null };
export type PortalDocumentRow = { id: string; document_id: string; title?: string | null; visible_for: string[]; sort_order: number };
export type ProviderRow = {
  id: string;
  contact_id: string;
  contact_name?: string | null;
  contract_type_code: string;
  valid_from: string;
  valid_to?: string | null;
  customer_number?: string | null;
  exemption_cert_status?: string | null;
  exemption_cert_valid_until?: string | null;
  creditor_account_id?: string | null;
  creditor_account_label?: string | null;
};

function Empty({ text }: { text: string }) {
  return <p className="mt-2 text-sm text-muted">{text}</p>;
}

export function BuildingsPanel({ buildings }: { buildings: BuildingRow[] }) {
  const t = useTranslations("Properties.buildings");
  const te = useTranslations("Properties.energyCertificate");
  return (
    <section className={ui.card} data-testid="property-buildings" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {buildings.length === 0 ? (
        <Empty text={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("name")}</th>
                <th>{t("address")}</th>
                <th>{t("addressAddition")}</th>
                <th className="num">{t("constructionYear")}</th>
                <th className="num">{t("floors")}</th>
                <th>{t("energyCertificate")}</th>
              </tr>
            </thead>
            <tbody>
              {buildings.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/objekte/${b.property_id}/gebaeude/${b.id}`} className="font-medium hover:underline" aria-label={`${t("open")}: ${b.name}`}>
                      {b.name}
                    </Link>
                  </td>
                  <td>{[b.street, b.house_number].filter(Boolean).join(" ")}</td>
                  <td>{b.address_addition ?? ""}</td>
                  <td className="num">{b.construction_year ?? ""}</td>
                  <td className="num">{b.floors ?? ""}</td>
                  <td>
                    {b.energy_certificate_type ? (
                      <>
                        {te(`types.${b.energy_certificate_type}`)}
                        {b.energy_certificate_class ? `, ${b.energy_certificate_class}` : ""}
                        {b.energy_certificate_valid_until ? `, ${te("validUntil")} ${formatDate(b.energy_certificate_valid_until)}` : ""}
                      </>
                    ) : (
                      <span className="text-muted">{t("noEnergyCertificate")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function BillingPeriodsPanel({ periods }: { periods: BillingPeriodRow[] }) {
  const t = useTranslations("Properties.billingPeriods");
  const tc = useTranslations("Inline");
  const kinds = [...new Set(periods.map((p) => p.kind))];
  return (
    <section className={ui.card} data-testid="property-billing-periods" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {periods.length === 0 ? (
        <Empty text={t("empty")} />
      ) : (
        kinds.map((kind) => (
          <div key={kind} className="mt-2">
            <h3 className={ui.subtitle}>{t(`kinds.${kind}`)}</h3>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("from")}</th>
                  <th>{t("to")}</th>
                  <th>{t("boardOnlineAudit")}</th>
                  <th>{t("notes")}</th>
                </tr>
              </thead>
              <tbody>
                {periods
                  .filter((p) => p.kind === kind)
                  .map((p) => (
                    <tr key={p.id}>
                      <td>{formatDate(p.valid_from)}</td>
                      <td>{formatDate(p.valid_to)}</td>
                      <td>{p.board_online_audit ? tc("yes") : tc("no")}</td>
                      <td>{p.notes ?? ""}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </section>
  );
}

export function SubCommunitiesPanel({ rows }: { rows: SubCommunityRow[] }) {
  const t = useTranslations("Properties.subCommunities");
  return (
    <section className={ui.card} data-testid="property-sub-communities" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.length === 0 ? (
        <Empty text={t("empty")} />
      ) : (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {rows.map((r) => (
            <li key={r.id}>
              <span className={ui.badgeGold}>{r.code}</span> {r.name}
              {r.notes ? <span className="text-muted">, {r.notes}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PortalDocumentsPanel({ rows }: { rows: PortalDocumentRow[] }) {
  const t = useTranslations("Properties.portalDocuments");
  return (
    <section className={ui.card} data-testid="property-portal-documents" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.length === 0 ? (
        <Empty text={t("empty")} />
      ) : (
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("document")}</th>
              <th>{t("visibleFor")}</th>
            </tr>
          </thead>
          <tbody>
            {[...rows]
              .sort((a, b) => a.sort_order - b.sort_order)
              .map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/dokumente/${r.document_id}`} className="hover:underline">
                      {r.title || r.document_id}
                    </Link>
                  </td>
                  <td>{r.visible_for.length ? r.visible_for.map((v) => t(`visibility.${v}`)).join(", ") : t("nobody")}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function ServiceProvidersPanel({ rows }: { rows: ProviderRow[] }) {
  const t = useTranslations("Properties.serviceProviders");
  const tu = useTranslations("Units");
  return (
    <section className={ui.card} data-testid="property-service-providers" aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      {rows.length === 0 ? (
        <Empty text={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("contact")}</th>
                <th>{t("contractType")}</th>
                <th>{t("validity")}</th>
                <th>{t("customerNumber")}</th>
                <th>{t("exemption")}</th>
                <th>{t("creditorAccount")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/kontakte/${r.contact_id}`} className="hover:underline">
                      {r.contact_name || r.contact_id}
                    </Link>
                  </td>
                  <td>{r.contract_type_code}</td>
                  <td>
                    {formatDate(r.valid_from)}
                    {r.valid_to ? ` ${tu("until")} ${formatDate(r.valid_to)}` : ""}
                  </td>
                  <td>{r.customer_number ?? ""}</td>
                  <td>
                    {t(`exemptionStatus.${r.exemption_cert_status ?? "unknown"}`)}
                    {r.exemption_cert_valid_until ? `, ${t("exemptionValidUntil", { date: formatDate(r.exemption_cert_valid_until) })}` : ""}
                  </td>
                  <td>{r.creditor_account_label ?? r.creditor_account_id ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
