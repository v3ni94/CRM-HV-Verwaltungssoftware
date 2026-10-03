"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";
import { formatDateTime } from "@/lib/format";

export type DomTenant = { id: string; slug: string; name: string; status: string };
type Domain = {
  id: string;
  host: string;
  purpose: string;
  cname_hint: string;
  verification_status?: string;
  verification_checked_at?: string | null;
  verification_finding?: string | null;
};

/** GA01-10: Kundendomains je Mandant (tenant_domain) und Mandantenstatus. */
export function TenantDomainsAdmin({ tenants }: { tenants: DomTenant[] }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("AA17.domains");
  const [list, setList] = useState<DomTenant[]>(tenants);
  const [tenantId, setTenantId] = useState(tenants[0]?.id ?? "");
  const [domains, setDomains] = useState<Domain[]>([]);
  const [host, setHost] = useState("");
  const [purpose, setPurpose] = useState("portal");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    const res = await bff<Domain[]>(`/api/bff/platform/tenants/${tenantId}/domains`);
    if (res.ok) setDomains(res.data);
    else setError(res.message);
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const res = await bff(`/api/bff/platform/tenants/${tenantId}/domains`, {
      method: "POST",
      body: JSON.stringify({ host, purpose }),
    });
    if (!res.ok) return setError(res.message);
    setHost("");
    await load();
  };

  const remove = async (id: string) => {
    setError(null);
    const res = await bff(`/api/bff/platform/tenants/${tenantId}/domains/${id}`, { method: "DELETE" });
    if (!res.ok) return setError(res.message);
    await load();
  };

  const verify = async (id: string) => {
    setError(null);
    const res = await bff<Domain>(`/api/bff/platform/domains/${id}/verify`, { method: "POST" });
    if (!res.ok) return setError(res.message);
    await load();
  };

  const current = list.find((x) => x.id === tenantId);
  const toggleStatus = async () => {
    if (!current) return;
    const next = current.status === "active" ? "suspended" : "active";
    if (next === "suspended" && !window.confirm(t("confirmSuspend"))) return;
    const res = await bff(`/api/bff/platform/tenants/${tenantId}`, {
      method: "PATCH",
      body: JSON.stringify({ status: next }),
    });
    if (!res.ok) return setError(res.message);
    setList((rows) => rows.map((r) => (r.id === tenantId ? { ...r, status: next } : r)));
  };

  return (
    <div className={`${ui.card} flex flex-col gap-4`}>
      <label htmlFor="aa17-tenant" className={ui.label}>
        {t("tenant")}
      </label>
      <select id="aa17-tenant" className={ui.input} value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
        {list.map((x) => (
          <option key={x.id} value={x.id}>
            {x.name}
          </option>
        ))}
      </select>
      {current ? (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span>
            {t("status")}: <span className={current.status === "active" ? ui.badgeSuccess : ui.badgeWarning}>{t(current.status === "active" ? "active" : "suspended")}</span>
          </span>
          <button disabled={busy} type="button" className={current.status === "active" ? ui.danger : ui.secondary} onClick={guard(() => toggleStatus())}>
            {t(current.status === "active" ? "suspend" : "activate")}
          </button>
        </div>
      ) : null}
      {domains.length === 0 ? (
        <p className={ui.help}>{t("none")}</p>
      ) : (
        <div className={ui.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>{t("host")}</th>
                <th>{t("purpose")}</th>
                <th>{t("cname")}</th>
                <th>{t("dnsStatus")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {domains.map((d) => (
                <tr key={d.id}>
                  <td>{d.host}</td>
                  <td>{t(`purposes.${d.purpose}`)}</td>
                  <td className={ui.mono}>{d.cname_hint}</td>
                  <td>
                    <span className={d.verification_status === "verified" ? ui.badgeSuccess : ui.badgeWarning}>
                      {t(`verification.${d.verification_status ?? "unverified"}`)}
                    </span>
                    {d.verification_checked_at ? (
                      <div className={ui.help}>
                        {formatDateTime(d.verification_checked_at)}
                        {d.verification_finding ? `: ${d.verification_finding}` : ""}
                      </div>
                    ) : null}
                  </td>
                  <td className="flex gap-2">
                    <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => verify(d.id))}>
                      {t("verify")}
                    </button>
                    <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => remove(d.id))}>
                      {t("remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form onSubmit={guard(add)} className="flex flex-wrap items-end gap-3" aria-label={t("add")}>
        <div>
          <label htmlFor="aa17-host" className={ui.label}>
            {t("host")}
          </label>
          <input id="aa17-host" className={ui.input} value={host} onChange={(e) => setHost(e.target.value)} required />
        </div>
        <div>
          <label htmlFor="aa17-purpose" className={ui.label}>
            {t("purpose")}
          </label>
          <select id="aa17-purpose" className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            {["portal", "crm", "api"].map((p) => (
              <option key={p} value={p}>
                {t(`purposes.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className={ui.primary}>
          {t("add")}
        </button>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
