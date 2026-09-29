"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Review list of CRM contact to Lexware contact links (INT-LEXO-01): every row is decided by
 *  a person; conflicts show CRM, Lexware and the last synced state side by side. */
export type LexofficeLink = {
  id: string;
  config_id: string;
  contact_id: string | null;
  contact_display_name: string | null;
  lexoffice_contact_id: string | null;
  customer_number: number | null;
  vendor_number: number | null;
  sync_status: string;
  diverged: boolean;
  remote_display: Record<string, unknown>;
  match_reason: string | null;
  match_score: string | number | null;
  candidates: { contact_id: string; reason: string; score: number }[];
  conflict: Record<string, { crm: unknown; lexoffice: unknown; baseline: unknown }> | null;
  last_synced_at: string | null;
  last_error: string | null;
  deeplink: string | null;
};

const FILTERS = ["proposed", "ambiguous", "remote_only", "conflict", "manual_required", "error", "diverged", "linked"] as const;
type Filter = (typeof FILTERS)[number];

function show(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("street" in record) return [record.street, record.zip, record.city, record.countryCode].filter(Boolean).join(", ");
    return Object.values(record).filter(Boolean).join(" ");
  }
  return String(value);
}

export function LexofficeContactLinks({ configId, canDecide }: { configId: string; canDecide: boolean }) {
  const t = useTranslations("Lexoffice");
  const [filter, setFilter] = useState<Filter>("proposed");
  const [scope, setScope] = useState<"customers_and_vendors" | "all">("customers_and_vendors");
  const [rows, setRows] = useState<LexofficeLink[]>([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<{ items: LexofficeLink[]; total: number }>(`/api/bff/integrations/lexoffice/configs/${configId}/contacts/links?status=${filter}&size=100`);
    if (res.ok) {
      setRows(res.data.items);
      setTotal(res.data.total);
    } else setError(res.message);
  }, [configId, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function post(path: string, body?: unknown) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<unknown>(`/api/bff/integrations/lexoffice/configs/${configId}/${path}`, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    await load();
    return true;
  }

  async function startMatch() {
    if (await post("contacts/match", { scope })) setMessage(t("links.started"));
  }

  async function batch() {
    const ids = rows.filter((r) => r.diverged && r.contact_id).map((r) => r.contact_id as string);
    if (ids.length === 0) return;
    if (!window.confirm(t("links.batchConfirm", { count: ids.length }))) return;
    await post("contacts/links/push-batch", { contact_ids: ids });
  }

  const divergedCount = rows.filter((r) => r.diverged).length;
  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("links.heading")}</h2>
      <p className={ui.help}>{t("links.intro")}</p>
      {canDecide ? (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="lx-scope" className={ui.label}>
              {t("links.scope")}
            </label>
            <select id="lx-scope" className={ui.input} value={scope} disabled={busy} onChange={(e) => setScope(e.target.value as typeof scope)}>
              <option value="customers_and_vendors">{t("links.scopeCustomers")}</option>
              <option value="all">{t("links.scopeAll")}</option>
            </select>
          </div>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void startMatch()}>
            {t("links.start")}
          </button>
          {filter === "diverged" && divergedCount > 0 ? (
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => void batch()}>
              {t("links.batch", { count: divergedCount })}
            </button>
          ) : null}
        </div>
      ) : null}
      <div>
        <label htmlFor="lx-link-filter" className={ui.label}>
          {t("links.filter")}
        </label>
        <select id="lx-link-filter" className={ui.input} value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          {FILTERS.map((f) => (
            <option key={f} value={f}>
              {t(`links.status.${f}`)}
            </option>
          ))}
        </select>
      </div>
      {rows.length === 0 ? <p className={ui.help}>{t("links.empty")}</p> : null}
      <ul className="flex flex-col gap-2">
        {rows.map((row) => {
          const remote = row.remote_display;
          const remoteName = String(remote.name ?? "");
          const decidable = ["proposed", "ambiguous", "remote_only", "remote_missing", "dismissed", "unlinked_local"].includes(row.sync_status);
          return (
            <li key={row.id} className="rounded border border-border p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">{row.contact_display_name ?? "—"}</span>
                  <span className="text-muted"> {"→"} </span>
                  <span>{remoteName}</span>
                  {row.customer_number ? <span className="text-muted"> {t("links.customerNumber", { number: row.customer_number })}</span> : null}
                  {remote.city ? <span className="text-muted"> {String(remote.city)}</span> : null}
                  {row.deeplink ? (
                    <>
                      {" "}
                      <a href={row.deeplink} target="_blank" rel="noreferrer" className="underline">
                        {t("links.openRemote")}
                      </a>
                    </>
                  ) : null}
                </div>
                <span className={ui.badge}>{t(`links.status.${row.sync_status}` as never)}</span>
              </div>
              <p className={ui.help}>
                {row.match_reason ? `${t("links.reason")}: ${t(`links.reasons.${row.match_reason}` as never)}` : null}
                {row.sync_status === "ambiguous" ? ` ${t("links.candidates", { count: row.candidates.length })}` : null}
                {row.diverged ? ` ${t("links.diverged")}` : null}
                {row.last_synced_at ? ` ${formatDateTime(row.last_synced_at)}` : null}
                {row.last_error ? ` ${row.last_error}` : null}
              </p>
              {row.conflict ? (
                <div className="mt-2">
                  <p className={ui.warning}>{t("links.conflictTitle")}</p>
                  <div className={ui.tableScroll}>
                    <table className={ui.table}>
                      <thead>
                        <tr>
                          <th />
                          <th>{t("links.conflictCrm")}</th>
                          <th>{t("links.conflictRemote")}</th>
                          <th>{t("links.conflictBaseline")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(row.conflict).map(([field, values]) => (
                          <tr key={field}>
                            <td>{field}</td>
                            <td>{show(values.crm)}</td>
                            <td>{show(values.lexoffice)}</td>
                            <td>{show(values.baseline)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {canDecide ? (
                    <div className={ui.formActions}>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/resolve-conflict`, { resolution: "keep_crm" })}>
                        {t("links.keepCrm")}
                      </button>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/resolve-conflict`, { resolution: "keep_lexoffice" })}>
                        {t("links.keepRemote")}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {canDecide ? (
                <div className={`${ui.formActions} mt-2`}>
                  {decidable && row.contact_id ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/decide`, { action: "link" })}>
                      {t("links.link")}
                    </button>
                  ) : null}
                  {decidable && row.sync_status === "remote_only" ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/decide`, { action: "create_local" })}>
                      {t("links.createLocal")}
                    </button>
                  ) : null}
                  {decidable && row.contact_id ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/decide`, { action: "create_remote", roles: ["customer"] })}>
                      {t("links.createRemote")} {t("links.roleCustomer")}
                    </button>
                  ) : null}
                  {decidable ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/decide`, { action: "dismiss" })}>
                      {t("links.dismiss")}
                    </button>
                  ) : null}
                  {["linked", "synced", "error"].includes(row.sync_status) ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/push`)}>
                      {t("links.push")}
                    </button>
                  ) : null}
                  {["error", "manual_required", "remote_missing"].includes(row.sync_status) ? (
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`contacts/links/${row.id}/retry`)}>
                      {t("links.retry")}
                    </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {total > rows.length ? <p className={ui.help}>{rows.length} / {total}</p> : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
