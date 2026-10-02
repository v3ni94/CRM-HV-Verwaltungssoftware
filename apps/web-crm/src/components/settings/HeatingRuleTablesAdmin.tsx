"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

export type RuleTable = {
  id: string;
  kind: "co2_steps" | "degree_days";
  valid_from: string;
  rows: unknown;
  source: string;
  review_status: "zu_pruefen" | "freigegeben";
  note: string | null;
};

const BASE = "/api/bff/billing/heating-rule-tables";

/** GAF-12: maintain the heating rule tables (CO2 steps, degree days). No values are
 *  prefilled: the operator enters rows and the official source, the API validates them. */
export function HeatingRuleTablesAdmin({ canManage }: { canManage: boolean }) {
  const { busy, guard } = useBusy();
  const t = useTranslations("BillingSetup.ruleTables");
  const [rows, setRows] = useState<RuleTable[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<RuleTable["kind"]>("co2_steps");
  const [validFrom, setValidFrom] = useState("");
  const [json, setJson] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState<RuleTable["review_status"]>("zu_pruefen");
  const [note, setNote] = useState("");
  const load = useCallback(async () => {
    const res = await bff<RuleTable[]>(BASE);
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  function edit(r: RuleTable) {
    setKind(r.kind);
    setValidFrom(r.valid_from);
    setJson(JSON.stringify(r.rows, null, 2));
    setSource(r.source);
    setStatus(r.review_status);
    setNote(r.note ?? "");
  }
  async function save() {
    setError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      return setError(t("invalidJson"));
    }
    const res = await bff(BASE, {
      method: "PUT",
      body: JSON.stringify({ kind, valid_from: validFrom, rows: parsed, source, review_status: status, note: note || null }),
    });
    if (!res.ok) return setError(res.message);
    await load();
  }
  return (
    <section className="flex flex-col gap-3" data-testid="heating-rule-tables">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows === null ? null : rows.length === 0 ? (
        <EmptyState title={t("empty")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("kind")}</th>
                <th>{t("validFrom")}</th>
                <th>{t("source")}</th>
                <th>{t("status")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{t(`kinds.${r.kind}`)}</td>
                  <td>{formatDate(r.valid_from)}</td>
                  <td>{r.source}</td>
                  <td>{t(`statuses.${r.review_status}`)}</td>
                  <td>
                    {canManage ? (
                      <button type="button" className={ui.secondary} onClick={() => edit(r)}>
                        {t("edit")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {canManage ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("kind")}</span>
            <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as RuleTable["kind"])}>
              <option value="co2_steps">{t("kinds.co2_steps")}</option>
              <option value="degree_days">{t("kinds.degree_days")}</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("validFrom")}</span>
            <input className={ui.input} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label className="sm:col-span-2 flex flex-col gap-1">
            <span className={ui.label}>{t("rows")}</span>
            <textarea className={ui.input} rows={6} value={json} onChange={(e) => setJson(e.target.value)} />
            <span className={ui.help}>{t(`rowsHint.${kind}`)}</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("source")}</span>
            <input className={ui.input} value={source} onChange={(e) => setSource(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("status")}</span>
            <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value as RuleTable["review_status"])}>
              <option value="zu_pruefen">{t("statuses.zu_pruefen")}</option>
              <option value="freigegeben">{t("statuses.freigegeben")}</option>
            </select>
          </label>
          <label className="sm:col-span-2 flex flex-col gap-1">
            <span className={ui.label}>{t("note")}</span>
            <input className={ui.input} value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div>
            <button type="button" className={ui.primary} disabled={busy || (!validFrom || source.trim().length < 3 || !json.trim())} onClick={guard(() => save())}>
              {t("save")}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
