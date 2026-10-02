"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of GET /api/v1/banking/automation/switch-requests and /comparison (AE03). */
export type SwitchRequest = {
  id: string;
  reason: string;
  status: "requested" | "approved" | "rejected";
  requested_by: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_comment: string | null;
  created_at: string;
};
export type SwitchState = { enabled: boolean; g1_open: boolean; can_request: boolean; items: SwitchRequest[] };
export type ComparisonReport = {
  outcomes: string[];
  totals: Record<string, number>;
  by_case_kind: Record<string, Record<string, number>>;
  compared_bookings: number;
  match_rate: string | null;
  rows: { decision_id: string; case_kind: string; outcome: string; decided_at: string | null }[];
};

const BASE = "/api/bff/banking/automation";

function percent(rate: string | null): string {
  if (rate === null) return "";
  const value = (Number(rate) * 100).toFixed(1).replace(".", ",");
  return `${value} %`;
}

/** Automatikschalter mit Freigabestufe G1 und Vier Augen sowie Vergleichsbericht Automatik
 *  gegen manuelle Buchung (Bericht, keine Buchung). Ausschalten bleibt über die API sofort. */
export function AutomationSwitch({ canApprove, userId }: { canApprove: boolean; userId: string | null }) {
  const t = useTranslations("Bank.automationSwitch");
  const [state, setState] = useState<SwitchState | null>(null);
  const [report, setReport] = useState<ComparisonReport | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const [s, r] = await Promise.all([
      bff<SwitchState>(`${BASE}/switch-requests`),
      bff<ComparisonReport>(`${BASE}/comparison`),
    ]);
    if (s.ok) setState(s.data);
    else setError(s.message);
    if (r.ok) setReport(r.data);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function act(path: string, body: unknown, done: string, method: "POST" | "PUT" = "POST") {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<unknown>(path, { method, body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setReason("");
    setMessage(done);
    await reload();
  }

  return (
    <div className="flex flex-col gap-4">
      <section className={ui.card} aria-labelledby="ae03-switch-title">
        <h2 id="ae03-switch-title" className={ui.h2}>
          {t("title")}
        </h2>
        <p className={ui.help}>{t("help")}</p>
        {message ? <p className={ui.success}>{message}</p> : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {state ? (
          <>
            <p className="mt-2 text-sm" data-testid="ae03-switch-state">
              <span className={state.enabled ? ui.badgeSuccess : ui.badge}>{state.enabled ? t("on") : t("off")}</span>{" "}
              <span className={state.g1_open ? ui.badgeSuccess : ui.badgeWarning}>{state.g1_open ? t("g1Open") : t("g1Closed")}</span>
            </p>
            {canApprove && state.enabled ? (
              <form
                className="mt-3 flex flex-col gap-2"
                data-testid="ae03-switch-off"
                onSubmit={(e) => {
                  e.preventDefault();
                  // AF01: PUT /banking/automation only switches off, at once and without request.
                  void act(BASE, { enabled: false, reason: reason.trim() }, t("switchedOff"), "PUT");
                }}
              >
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("offReason")}</span>
                  <textarea className={ui.input} rows={2} required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <div className={ui.formActions}>
                  <button type="submit" className={ui.danger} disabled={busy || reason.trim().length < 3}>
                    {t("switchOff")}
                  </button>
                </div>
              </form>
            ) : null}
            {canApprove && state.can_request ? (
              <form
                className="mt-3 flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(`${BASE}/switch-requests`, { reason: reason.trim() }, t("requested"));
                }}
              >
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("reason")}</span>
                  <textarea className={ui.input} rows={2} required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <div className={ui.formActions}>
                  <button type="submit" className={ui.primary} disabled={busy || reason.trim().length < 3}>
                    {t("request")}
                  </button>
                </div>
              </form>
            ) : (
              <p className={ui.help}>{!state.g1_open ? t("blockedG1") : state.enabled ? t("alreadyOn") : t("pendingOrNoRight")}</p>
            )}
            {state.items.length > 0 ? (
              <ul className="mt-3 flex flex-col gap-2 text-sm" data-testid="ae03-switch-requests">
                {state.items.map((r) => (
                  <li key={r.id}>
                    <span className={ui.badge}>{t(`status.${r.status}`)}</span> {r.reason}
                    {r.status === "requested" && canApprove && r.requested_by !== userId ? (
                      <span className="ml-2 inline-flex gap-2">
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void act(`${BASE}/switch-requests/${r.id}/approve`, {}, t("approved"))}>
                          {t("approve")}
                        </button>
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void act(`${BASE}/switch-requests/${r.id}/reject`, {}, t("rejected"))}>
                          {t("reject")}
                        </button>
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </section>

      <section className={ui.card} aria-labelledby="ae03-comparison-title">
        <h2 id="ae03-comparison-title" className={ui.h2}>
          {t("comparison.title")}
        </h2>
        <p className={ui.help}>{t("comparison.help")}</p>
        {report ? (
          <>
            <p className="mt-2 text-sm" data-testid="ae03-comparison-summary">
              {t("comparison.summary", { compared: report.compared_bookings, rate: percent(report.match_rate) || t("comparison.noRate") })}
            </p>
            <div className={ui.tableScroll}>
              <table className={ui.table} data-testid="ae03-comparison-table">
                <thead>
                  <tr>
                    <th>{t("comparison.caseKind")}</th>
                    {report.outcomes.map((o) => (
                      <th key={o}>{t(`comparison.outcome.${o}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>{t("comparison.total")}</td>
                    {report.outcomes.map((o) => (
                      <td key={o} className={ui.num}>
                        {report.totals[o] ?? 0}
                      </td>
                    ))}
                  </tr>
                  {Object.entries(report.by_case_kind).map(([kind, counts]) => (
                    <tr key={kind}>
                      <td>{kind}</td>
                      {report.outcomes.map((o) => (
                        <td key={o} className={ui.num}>
                          {counts[o] ?? 0}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}
