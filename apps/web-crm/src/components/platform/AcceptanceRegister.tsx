"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of GET /api/v1/accounting/acceptance/cases (V16, AE01). */
export type AcceptanceExpected = {
  id: string;
  case_id: string;
  version: number;
  title: string;
  inputs: Record<string, unknown>;
  expected: Record<string, unknown>;
  source: string;
  calculation: string | null;
  status: "draft" | "submitted" | "approved" | "rejected" | "superseded";
  approved_by_name: string | null;
  approved_at: string | null;
};
export type AcceptanceResult = { id: string; outcome: "passed" | "failed"; software_version: string; decided_by_name: string; decided_at: string };
export type AcceptanceCase = {
  case_id: string;
  g1_scope: boolean;
  current: AcceptanceExpected | null;
  released: AcceptanceExpected | null;
  last_result: AcceptanceResult | null;
};
export type AcceptanceState = { note: string; cases_total: number; released_total: number; passed_total: number; items: AcceptanceCase[] };

const BASE = "/api/bff/accounting/acceptance";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

/** Abnahmeregister: unabhängige Sollwerte je Anhang-D-Fall, Freigabe durch eine zweite Person
 *  mit dem Recht Abnahme freigeben, Ergebnis je freigegebener Fassung, Export als Markdown.
 *  Die Seite öffnet keine Freigabestufe. */
export function AcceptanceRegister({
  initial,
  canManage,
  canApprove,
}: {
  initial: AcceptanceState | null;
  canManage: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("AE01");
  const tCommon = useTranslations("Common");
  const [state, setState] = useState<AcceptanceState | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", inputs: "{}", expected: "{}", source: "", calculation: "" });
  const [name, setName] = useState("");
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload() {
    const res = await bff<AcceptanceState>(`${BASE}/cases`);
    if (res.ok) setState(res.data);
  }

  async function run(path: string, body?: unknown) {
    if (busy) return false;
    setBusy(true);
    setError(null);
    const res = await bff(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    await reload();
    return true;
  }

  async function saveDraft() {
    if (!editing) return;
    let inputs: unknown;
    let expected: unknown;
    try {
      inputs = JSON.parse(form.inputs);
      expected = JSON.parse(form.expected);
    } catch {
      setError(t("jsonInvalid"));
      return;
    }
    const ok = await run(`${BASE}/cases/${editing}/expected`, {
      title: form.title,
      inputs,
      expected,
      source: form.source,
      calculation: form.calculation || null,
    });
    if (ok) setEditing(null);
  }

  if (!state) return <p className={ui.alert}>{t("loadError")}</p>;
  return (
    <div className="flex flex-col gap-4">
      <p className={ui.alert} data-testid="ae01-note">{state.note}</p>
      <p data-testid="ae01-counts">
        {t("counts", { released: state.released_total, passed: state.passed_total, total: state.cases_total })}
      </p>
      <a className="underline" href={`${BASE}/export.md`}>{t("export")}</a>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {canApprove ? (
        <div className="flex flex-wrap gap-2">
          <label className="flex flex-col">
            {t("name")}
            <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="flex flex-col">
            {t("softwareVersion")}
            <input className={ui.input} value={version} onChange={(e) => setVersion(e.target.value)} />
          </label>
        </div>
      ) : null}
      {editing ? (
        <div className="flex flex-col gap-2" data-testid="ae01-form">
          <h3>{t("draftFor", { case: editing })}</h3>
          <label className="flex flex-col">{t("fieldTitle")}<input className={ui.input} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="flex flex-col">{t("fieldInputs")}<textarea className={ui.input} value={form.inputs} onChange={(e) => setForm({ ...form, inputs: e.target.value })} /></label>
          <label className="flex flex-col">{t("fieldExpected")}<textarea className={ui.input} value={form.expected} onChange={(e) => setForm({ ...form, expected: e.target.value })} /></label>
          <label className="flex flex-col">{t("fieldSource")}<input className={ui.input} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /></label>
          <label className="flex flex-col">{t("fieldCalculation")}<textarea className={ui.input} value={form.calculation} onChange={(e) => setForm({ ...form, calculation: e.target.value })} /></label>
          <p className="text-sm">{t("amountHint")}</p>
          <div className="flex gap-2">
            <button type="button" className={ui.button} disabled={busy} onClick={() => void saveDraft()}>{t("saveDraft")}</button>
            <button type="button" className={ui.button} onClick={() => setEditing(null)}>{t("cancel")}</button>
          </div>
        </div>
      ) : null}
      <div className={ui.tableScroll}>
      <table className="w-full text-sm" data-testid="ae01-table">
        <thead>
          <tr>
            <th>{t("colCase")}</th><th>{t("colTitle")}</th><th>{t("colStatus")}</th><th>{t("colReleased")}</th><th>{t("colResult")}</th><th>{t("colActions")}</th>
          </tr>
        </thead>
        <tbody>
          {state.items.length === 0 ? (
            <tr>
              <td colSpan={99} className="text-muted">
                {tCommon("emptyList")}
              </td>
            </tr>
          ) : null}
          {state.items.map((item) => {
            const cur = item.current;
            const rel = item.released;
            return (
              <tr key={item.case_id} data-testid={`ae01-row-${item.case_id}`}>
                <td>{item.case_id}{item.g1_scope ? " (G1)" : ""}</td>
                <td>{cur?.title ?? ""}</td>
                <td>{cur ? t(`status.${cur.status}`) : t("status.none")}</td>
                <td>{rel ? t("releasedBy", { version: rel.version, name: rel.approved_by_name ?? "", date: formatDate(rel.approved_at) }) : ""}</td>
                <td>{item.last_result ? t(`outcome.${item.last_result.outcome}`) : ""}</td>
                <td className="flex flex-wrap gap-1">
                  {canManage && (!cur || cur.status !== "draft") ? (
                    <button type="button" className={ui.button} onClick={() => { setEditing(item.case_id); setForm({ title: cur?.title ?? "", inputs: "{}", expected: "{}", source: "", calculation: "" }); }}>{t("newVersion")}</button>
                  ) : null}
                  {canManage && cur?.status === "draft" ? (
                    <button type="button" className={ui.button} disabled={busy} onClick={() => void run(`${BASE}/expected/${cur.id}/submit`)}>{t("submit")}</button>
                  ) : null}
                  {canApprove && cur?.status === "submitted" ? (
                    <>
                      <button type="button" className={ui.button} disabled={!name || busy} onClick={() => void run(`${BASE}/expected/${cur.id}/decision`, { decision: "approve", name })}>{t("approve")}</button>
                      <button type="button" className={ui.button} disabled={!name || busy} onClick={() => void run(`${BASE}/expected/${cur.id}/decision`, { decision: "reject", name })}>{t("reject")}</button>
                    </>
                  ) : null}
                  {canApprove && rel ? (
                    <>
                      <button type="button" className={ui.button} disabled={!name || !version || busy} onClick={() => void run(`${BASE}/expected/${rel.id}/results`, { outcome: "passed", software_version: version, name })}>{t("passed")}</button>
                      <button type="button" className={ui.button} disabled={!name || !version || busy} onClick={() => void run(`${BASE}/expected/${rel.id}/results`, { outcome: "failed", software_version: version, name })}>{t("failed")}</button>
                    </>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}
