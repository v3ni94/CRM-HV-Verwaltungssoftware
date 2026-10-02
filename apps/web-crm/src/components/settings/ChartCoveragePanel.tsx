"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import type { ChartTemplate } from "./ChartReleaseAdmin";
import { useBusy } from "@/lib/use-busy";

/** AE02 (M10-01, SA-08, P07-04, P07-05): four eyes switch, coverage report and the multi key
 * distribution editor of a draft chart of accounts version. */
type CoverageAccount = { number: string; name: string; issues: string[]; proposed_statement_kind: string | null };
type Coverage = {
  accounts_total: number;
  without_statement_kind: number;
  without_allocation: number;
  open_proposals: number;
  statement_kinds_without_account: string[];
  accounts: CoverageAccount[];
};
type SplitRow = { key_code: string; share_percent: string };

const BASE = "/api/bff/accounting/templates";

export function ChartCoveragePanel({
  template,
  canManage,
  canApprove,
  onChanged,
}: {
  template: ChartTemplate;
  canManage: boolean;
  canApprove: boolean;
  onChanged: () => Promise<void>;
}) {
  const { busy, guard } = useBusy();
  const t = useTranslations("ChartRelease.coverage");
  const [report, setReport] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [split, setSplit] = useState<SplitRow[]>([]);
  const isDraft = template.status === "draft";
  const fourEyes = template.four_eyes_required !== false;

  async function loadReport() {
    setError(null);
    const res = await bff<Coverage>(`${BASE}/${template.id}/coverage-report`);
    if (res.ok) setReport(res.data);
    else setError(res.message);
  }

  async function toggleFourEyes() {
    setError(null);
    const res = await bff<ChartTemplate>(`${BASE}/${template.id}/four-eyes`, {
      method: "PUT",
      body: JSON.stringify({ required: !fourEyes, reason: reason.trim() }),
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setReason("");
    await onChanged();
  }

  function startEdit(number: string) {
    const row = template.accounts.find((r) => r.number === number);
    const current = (row?.allocation_split as SplitRow[] | undefined) ?? [];
    setSplit(current.length ? current.map((s) => ({ ...s })) : [{ key_code: "", share_percent: "100" }]);
    setEditing(number);
  }

  async function saveAccounts(change: (row: Record<string, unknown>) => Record<string, unknown>, number: string) {
    setError(null);
    const accounts = template.accounts.map((row) => (row.number === number ? change({ ...row }) : row));
    const res = await bff<ChartTemplate>(`${BASE}/${template.id}/accounts`, {
      method: "PUT",
      body: JSON.stringify({ accounts }),
    });
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    await onChanged();
    if (report) await loadReport();
    return true;
  }

  async function saveSplit() {
    if (!editing) return;
    const ok = await saveAccounts(
      (row) => ({ ...row, allocation_split: split.filter((s) => s.key_code.trim()).map((s) => ({ key_code: s.key_code.trim(), share_percent: s.share_percent.trim() })) }),
      editing,
    );
    if (ok) setEditing(null);
  }

  const sum = split.reduce((acc, s) => acc + (Number(s.share_percent.replace(",", ".")) || 0), 0);

  return (
    <div className="mt-4" data-testid="chart-coverage">
      <h3 className={ui.h3}>{t("title")}</h3>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <p className={`${ui.small} mt-1`}>{fourEyes ? t("fourEyesOn") : t("fourEyesOff")}</p>
      {canApprove && template.status !== "released" ? (
        <div className={`${ui.formActions} mt-1`}>
          <input
            aria-label={t("reasonLabel")}
            className={ui.input}
            value={reason}
            placeholder={t("reasonLabel")}
            onChange={(e) => setReason(e.target.value)}
          />
          <button type="button" className={ui.button} disabled={busy || (reason.trim().length < 3)} onClick={guard(toggleFourEyes)}>
            {fourEyes ? t("fourEyesDisable") : t("fourEyesEnable")}
          </button>
        </div>
      ) : null}
      <button disabled={busy} type="button" className={`${ui.button} mt-2`} onClick={guard(loadReport)}>
        {t("load")}
      </button>
      {report ? (
        <div className="mt-2">
          <p className={ui.small}>
            {t("summary", {
              total: report.accounts_total,
              kind: report.without_statement_kind,
              alloc: report.without_allocation,
              open: report.open_proposals,
            })}
          </p>
          {report.statement_kinds_without_account.length ? (
            <p className={ui.notice}>{t("kindsWithoutAccount", { kinds: report.statement_kinds_without_account.join(", ") })}</p>
          ) : null}
          <div className="mt-1 overflow-x-auto">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("colNumber")}</th>
                  <th>{t("colName")}</th>
                  <th>{t("colIssues")}</th>
                  <th>{t("colProposal")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {report.accounts.map((a) => (
                  <tr key={a.number}>
                    <td className={ui.mono}>{a.number}</td>
                    <td>{a.name}</td>
                    <td>{a.issues.map((i) => t(`issue.${i}`)).join(", ")}</td>
                    <td>{a.proposed_statement_kind ? `${a.proposed_statement_kind} (${t("proposalOpen")})` : ""}</td>
                    <td>
                      {canManage && isDraft ? (
                        <span className="flex gap-1">
                          {a.issues.includes("vorschlag_offen") ? (
                            <button
                              type="button"
                              className={ui.button}
                              onClick={() =>
                                saveAccounts(
                                  (row) => ({ ...row, statement_kind: a.proposed_statement_kind, proposal_status: "uebernommen" }),
                                  a.number,
                                )
                              }
                            >
                              {t("adopt")}
                            </button>
                          ) : null}
                          <button type="button" className={ui.button} onClick={() => startEdit(a.number)}>
                            {t("editSplit")}
                          </button>
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {editing ? (
        <form
          className={`${ui.card} mt-2`}
          aria-label={t("splitTitle", { number: editing })}
          onSubmit={(e) => {
            e.preventDefault();
            void saveSplit();
          }}
        >
          <h4 className={ui.h3}>{t("splitTitle", { number: editing })}</h4>
          {split.map((s, i) => (
            <div key={i} className={`${ui.formActions} mt-1`}>
              <input
                aria-label={t("keyCode")}
                className={ui.input}
                value={s.key_code}
                onChange={(e) => setSplit(split.map((x, j) => (j === i ? { ...x, key_code: e.target.value } : x)))}
              />
              <input
                aria-label={t("share")}
                className={ui.input}
                inputMode="decimal"
                value={s.share_percent}
                onChange={(e) => setSplit(split.map((x, j) => (j === i ? { ...x, share_percent: e.target.value } : x)))}
              />
              <button type="button" className={ui.button} onClick={() => setSplit(split.filter((_, j) => j !== i))}>
                {t("removeRow")}
              </button>
            </div>
          ))}
          <p className={ui.help}>{t("sum", { sum: sum.toLocaleString("de-DE") })}</p>
          <div className={`${ui.formActions} mt-2`}>
            <button disabled={busy} type="button" className={ui.button} onClick={() => setSplit([...split, { key_code: "", share_percent: "" }])}>
              {t("addRow")}
            </button>
            <button type="submit" className={ui.primary}>
              {t("saveSplit")}
            </button>
            <button type="button" className={ui.button} onClick={() => setEditing(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
