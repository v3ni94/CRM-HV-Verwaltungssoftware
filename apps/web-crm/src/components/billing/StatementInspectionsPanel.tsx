"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

export type InspectionContract = { contract_id: string; unit_number: string };
type Inspection = {
  id: string;
  contract_id: string;
  requested_at: string;
  channel: string;
  status: string;
  provision: string | null;
  provided_at: string | null;
  objection_received_at: string | null;
  objection_text: string | null;
};

const CHANNELS = ["letter", "email", "phone", "portal", "in_person"] as const;
const PROVISIONS = ["electronic", "copies", "appointment"] as const;

/** GAF-13: record requests to inspect the receipts (rental statement), their provision and
 *  objections. Loaded on demand. Records only, no legal effect and no deadline calculation. */
export function StatementInspectionsPanel({ id, contracts }: { id: string; contracts: InspectionContract[] }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("BillingExtra.inspections");
  const base = `/api/bff/statements/${id}/inspections`;
  const [rows, setRows] = useState<Inspection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [contract, setContract] = useState(contracts[0]?.contract_id ?? "");
  const [requestedAt, setRequestedAt] = useState("");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("letter");
  const [provision, setProvision] = useState<(typeof PROVISIONS)[number]>("electronic");
  const [providedAt, setProvidedAt] = useState("");
  const [objection, setObjection] = useState("");
  const [objectionAt, setObjectionAt] = useState("");
  const unit = (cid: string) => contracts.find((c) => c.contract_id === cid)?.unit_number ?? cid;
  async function load() {
    setError(null);
    const res = await bff<Inspection[]>(base);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }
  async function create() {
    setError(null);
    const res = await bff(base, {
      method: "POST",
      body: JSON.stringify({ contract_id: contract, requested_at: requestedAt, channel }),
    });
    if (!res.ok) return setError(res.message);
    setRequestedAt("");
    await load();
  }
  async function patch(rowId: string, body: Record<string, unknown>) {
    setError(null);
    const res = await bff(`${base}/${rowId}`, { method: "PATCH", body: JSON.stringify(body) });
    if (!res.ok) return setError(res.message);
    await load();
  }
  return (
    <section className="flex flex-col gap-2" data-testid="statement-inspections">
      <h3 className={ui.h2}>{t("title")}</h3>
      <p className={ui.notice}>{t("notice")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => load())}>
          {t("load")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? null : (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("unit")}</span>
              <select className={ui.input} value={contract} onChange={(e) => setContract(e.target.value)}>
                {contracts.map((c) => (
                  <option key={c.contract_id} value={c.contract_id}>
                    {c.unit_number}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("requestedAt")}</span>
              <input className={ui.input} type="date" value={requestedAt} onChange={(e) => setRequestedAt(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("channel")}</span>
              <select className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as (typeof CHANNELS)[number])}>
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {t(`channels.${c}`)}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className={ui.button} disabled={busy || (!contract || !requestedAt)} onClick={guard(() => create())}>
              {t("add")}
            </button>
          </div>
          {rows.length === 0 ? (
            <p className={ui.help}>{t("empty")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="mhvp-table">
                <thead>
                  <tr>
                    <th>{t("unit")}</th>
                    <th>{t("requestedAt")}</th>
                    <th>{t("channel")}</th>
                    <th>{t("status")}</th>
                    <th>{t("provision")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>{unit(r.contract_id)}</td>
                      <td>{formatDate(r.requested_at)}</td>
                      <td>{t(`channels.${r.channel}`)}</td>
                      <td>{r.status === "closed" ? t("closed") : t("open")}</td>
                      <td>
                        {r.provision ? `${t(`provisions.${r.provision}`)} ${formatDate(r.provided_at)}` : ""}
                        {r.objection_received_at ? ` ${t("objection")} ${formatDate(r.objection_received_at)}` : ""}
                      </td>
                      <td className="flex flex-wrap gap-1">
                        {r.status === "closed" ? null : (
                          <>
                            <select className={ui.input} aria-label={t("provision")} value={provision} onChange={(e) => setProvision(e.target.value as (typeof PROVISIONS)[number])}>
                              {PROVISIONS.map((p) => (
                                <option key={p} value={p}>
                                  {t(`provisions.${p}`)}
                                </option>
                              ))}
                            </select>
                            <input className={ui.input} type="date" aria-label={t("providedAt")} value={providedAt} onChange={(e) => setProvidedAt(e.target.value)} />
                            <button type="button" className={ui.secondary} disabled={busy || (!providedAt)} onClick={guard(() => patch(r.id, { provision, provided_at: providedAt }))}>
                              {t("provide")}
                            </button>
                            <input className={ui.input} type="date" aria-label={t("objectionDate")} value={objectionAt} onChange={(e) => setObjectionAt(e.target.value)} />
                            <input className={ui.input} aria-label={t("objectionText")} placeholder={t("objectionText")} value={objection} onChange={(e) => setObjection(e.target.value)} />
                            <button
                              type="button"
                              className={ui.secondary}
                              disabled={busy || (!objection.trim() || !objectionAt)}
                              onClick={guard(() => patch(r.id, { objection_received_at: objectionAt, objection_text: objection }))}
                            >
                              {t("recordObjection")}
                            </button>
                            <button disabled={busy} type="button" className={ui.secondary} onClick={guard(() => patch(r.id, { close: true }))}>
                              {t("close")}
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
