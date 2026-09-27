"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { switchTenant } from "@/components/auth/TenantPicker";
import { StatusChip } from "@/components/ui/StatusChip";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Shapes of GET /api/v1/platform/overview, /tickets and /properties (M2-05). Read only:
 *  every row carries its tenant; writing needs the recorded tenant switch. */
export type TenantFigures = {
  tenant_id: string;
  tenant_name: string;
  properties: number;
  units: number;
  open_tickets: number;
  deadlines_due: number;
  open_approvals: number;
  approvals: Record<string, number>;
};

export type OverviewData = { tenants: TenantFigures[]; totals: Record<string, number> };

export type OverviewTicket = {
  tenant_id: string;
  tenant_name: string;
  id: string;
  number: number;
  title: string;
  status: string;
  priority: string;
  sla_due_at: string | null;
  due_on: string | null;
  property_id: string | null;
  created_at: string;
};

export type OverviewProperty = {
  tenant_id: string;
  tenant_name: string;
  id: string;
  number: string;
  name: string;
  city: string | null;
  management_type: string;
  status: string;
  units: number;
  open_tickets: number;
};

type Props = {
  currentTenantId: string | null;
  overview: OverviewData;
  tickets: OverviewTicket[];
  properties: OverviewProperty[];
};

const ALL = "all";
const FIGURES: (keyof Omit<TenantFigures, "tenant_id" | "tenant_name" | "approvals">)[] = [
  "properties",
  "units",
  "open_tickets",
  "deadlines_due",
  "open_approvals",
];

/** "Im Mandanten öffnen": switches to the row's tenant (new session, recorded like every
 *  switch) and then navigates to the record. In the current tenant it is a plain navigation. */
export function OpenInTenant({
  tenantId,
  currentTenantId,
  href,
  onError,
}: {
  tenantId: string;
  currentTenantId: string | null;
  href: string;
  onError: (message: string) => void;
}) {
  const t = useTranslations("PlatformOverview");
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function open() {
    if (tenantId !== currentTenantId) {
      setBusy(true);
      const result = await switchTenant(tenantId);
      setBusy(false);
      if (!result.ok) {
        onError(result.message);
        return;
      }
    }
    router.push(href);
    router.refresh();
  }

  return (
    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void open()}>
      {t("openInTenant")}
    </button>
  );
}

export function PlatformOverview({ currentTenantId, overview, tickets, properties }: Props) {
  const t = useTranslations("PlatformOverview");
  const [selected, setSelected] = useState<string>(ALL);
  const [error, setError] = useState<string | null>(null);

  const visibleTenants = useMemo(
    () => (selected === ALL ? overview.tenants : overview.tenants.filter((x) => x.tenant_id === selected)),
    [overview.tenants, selected],
  );
  const visibleTickets = useMemo(
    () => (selected === ALL ? tickets : tickets.filter((x) => x.tenant_id === selected)),
    [tickets, selected],
  );
  const visibleProperties = useMemo(
    () => (selected === ALL ? properties : properties.filter((x) => x.tenant_id === selected)),
    [properties, selected],
  );

  if (overview.tenants.length === 0) {
    return <p className={ui.notice}>{t("noMembership")}</p>;
  }

  return (
    <div className={ui.sectionGap}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("switcher")}>
        <span className={ui.label}>{t("switcher")}</span>
        <button
          type="button"
          className={selected === ALL ? ui.primary : ui.secondary}
          aria-pressed={selected === ALL}
          onClick={() => setSelected(ALL)}
        >
          {t("allTenants")}
        </button>
        {overview.tenants.map((tn) => (
          <button
            key={tn.tenant_id}
            type="button"
            className={selected === tn.tenant_id ? ui.primary : ui.secondary}
            aria-pressed={selected === tn.tenant_id}
            onClick={() => setSelected(tn.tenant_id)}
          >
            {tn.tenant_name}
            {tn.tenant_id === currentTenantId ? ` (${t("current")})` : ""}
          </button>
        ))}
      </div>

      <section className={ui.card} aria-labelledby="ov-figures">
        <h2 id="ov-figures" className={ui.h2}>
          {t("figures")}
        </h2>
        <div className="mt-2 overflow-x-auto">
          <table className={ui.table} data-testid="overview-figures">
            <thead>
              <tr>
                <th scope="col">{t("figure")}</th>
                {visibleTenants.map((tn) => (
                  <th key={tn.tenant_id} scope="col">
                    {tn.tenant_name}
                  </th>
                ))}
                {selected === ALL ? <th scope="col">{t("total")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {FIGURES.map((key) => (
                <tr key={key}>
                  <th scope="row">{t(`figures_${key}`)}</th>
                  {visibleTenants.map((tn) => (
                    <td key={tn.tenant_id} className={ui.num}>
                      {tn[key]}
                    </td>
                  ))}
                  {selected === ALL ? <td className={ui.num}>{overview.totals[key] ?? 0}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={ui.card} aria-labelledby="ov-tickets">
        <h2 id="ov-tickets" className={ui.h2}>
          {t("tickets")}
        </h2>
        {visibleTickets.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("noTickets")}</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className={ui.table} data-testid="overview-tickets">
              <thead>
                <tr>
                  <th scope="col">{t("tenant")}</th>
                  <th scope="col">{t("number")}</th>
                  <th scope="col">{t("title_")}</th>
                  <th scope="col">{t("priority")}</th>
                  <th scope="col">{t("status")}</th>
                  <th scope="col">{t("slaDue")}</th>
                  <th scope="col">{t("dueOn")}</th>
                  <th scope="col">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {visibleTickets.map((row) => (
                  <tr key={`${row.tenant_id}-${row.id}`}>
                    <td>
                      <span className={ui.badge}>{row.tenant_name}</span>
                    </td>
                    <td className={ui.num}>{row.number}</td>
                    <td>{row.title}</td>
                    <td>
                      <StatusChip domain="ticketPriority" status={row.priority} />
                    </td>
                    <td>
                      <StatusChip domain="ticket" status={row.status} />
                    </td>
                    <td>{formatDateTime(row.sla_due_at)}</td>
                    <td>{formatDate(row.due_on)}</td>
                    <td>
                      <OpenInTenant
                        tenantId={row.tenant_id}
                        currentTenantId={currentTenantId}
                        href={`/tickets/${row.id}`}
                        onError={setError}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={ui.card} aria-labelledby="ov-properties">
        <h2 id="ov-properties" className={ui.h2}>
          {t("properties")}
        </h2>
        {visibleProperties.length === 0 ? (
          <p className="mt-2 text-sm text-muted">{t("noProperties")}</p>
        ) : (
          <div className="mt-2 overflow-x-auto">
            <table className={ui.table} data-testid="overview-properties">
              <thead>
                <tr>
                  <th scope="col">{t("tenant")}</th>
                  <th scope="col">{t("number")}</th>
                  <th scope="col">{t("name")}</th>
                  <th scope="col">{t("city")}</th>
                  <th scope="col">{t("units")}</th>
                  <th scope="col">{t("openTickets")}</th>
                  <th scope="col">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {visibleProperties.map((row) => (
                  <tr key={`${row.tenant_id}-${row.id}`}>
                    <td>
                      <span className={ui.badge}>{row.tenant_name}</span>
                    </td>
                    <td className={ui.mono}>{row.number}</td>
                    <td>{row.name}</td>
                    <td>{row.city ?? ""}</td>
                    <td className={ui.num}>{row.units}</td>
                    <td className={ui.num}>{row.open_tickets}</td>
                    <td>
                      <OpenInTenant
                        tenantId={row.tenant_id}
                        currentTenantId={currentTenantId}
                        href={`/objekte/${row.id}`}
                        onError={setError}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
